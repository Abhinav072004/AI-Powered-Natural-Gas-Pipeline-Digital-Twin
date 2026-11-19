"""MQTT contract validation and PostgreSQL/TimescaleDB persistence."""

from datetime import datetime
import logging
import os
import time
from typing import Annotated, Literal

import paho.mqtt.client as mqtt
import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, StringConstraints, ValidationError, model_validator

TOPIC = "prototype/telemetry/v1"
log = logging.getLogger(__name__)
Identifier = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_.:-]{1,80}$")]


class Telemetry(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    schema_version: Literal[1]
    run_id: Identifier
    message_id: Identifier
    sensor_id: Identifier
    segment_id: int = Field(ge=1)
    boundary_index: int | None = Field(ge=0)
    observed_at: AwareDatetime
    value: float | None
    unit: Literal["Pa(a)", "kg/s", "K", "mm/s", "W", "boolean"]
    quality: Literal["good", "missing", "invalid"]

    @model_validator(mode="after")
    def validate_reading(self):
        if (self.quality == "good") != (self.value is not None):
            raise ValueError("A usable value is required exactly when quality is good")
        if self.value is not None and self.unit == "boolean" and self.value not in (0, 1):
            raise ValueError("Boolean indications must be zero or one")
        if self.sensor_id.startswith("PT-") and self.unit != "Pa(a)":
            raise ValueError("Pressure readings must use absolute pascals")
        if self.sensor_id.startswith("FT-") and self.unit != "kg/s":
            raise ValueError("Flow readings must use kg/s")
        if self.sensor_id.startswith("TT-") and self.unit != "K":
            raise ValueError("Temperature readings must use kelvin")
        return self


class Store:
    def __init__(self, url: str | None):
        self.url = url

    def connect(self):
        return psycopg.connect(self.url, row_factory=dict_row, connect_timeout=4)

    def check(self):
        with self.connect() as conn:
            conn.execute("SELECT 1 FROM telemetry LIMIT 1")

    def insert(self, reading: Telemetry):
        with self.connect() as conn:
            conn.execute(
                """
                INSERT INTO telemetry (observed_at, run_id, message_id, sensor_id, envelope)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT (observed_at, run_id, message_id) DO NOTHING
                """,
                (reading.observed_at, reading.run_id, reading.message_id,
                 reading.sensor_id, Jsonb(reading.model_dump(mode="json"))),
            )

    def latest(self, run_id: str | None, limit: int = 32) -> tuple[str | None, list[dict], datetime | None]:
        if self.url is None:
            return None, [], None
        with self.connect() as conn:
            if run_id is None:
                latest = conn.execute("SELECT run_id FROM telemetry ORDER BY received_at DESC LIMIT 1").fetchone()
                if not latest:
                    return None, [], None
                run_id = latest["run_id"]
            rows = conn.execute(
                """
                SELECT observed_at, max(received_at) AS arrived,
                       jsonb_agg(envelope ORDER BY sensor_id) AS readings
                FROM telemetry WHERE run_id = %s GROUP BY observed_at
                ORDER BY observed_at DESC LIMIT %s
                """,
                (run_id, limit),
            ).fetchall()
        return run_id, [
            {"observed_at": row["observed_at"].isoformat(), "readings": row["readings"]}
            for row in reversed(rows)
        ], max((row["arrived"] for row in rows), default=None)

    def save_review(self, assessment: dict, note: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                """
                INSERT INTO risk_review (hazard, probability, severity, note)
                VALUES (%s, %s, %s, %s) RETURNING review_id, reviewed_at
                """,
                (assessment["hazard"], assessment["probability"], assessment["severity"], note),
            ).fetchone()
        return dict(assessment, **row, note=note)


def consume():
    logging.basicConfig(level=logging.INFO)
    store = Store(os.environ["DATABASE_URL"])
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id="pipeline-ingestion-v1",
                         clean_session=False, manual_ack=True)
    if username := os.getenv("MQTT_USERNAME"):
        client.username_pw_set(username, os.environ["MQTT_PASSWORD"])

    @client.connect_callback()
    def connected(client, userdata, flags, reason_code, properties):
        if not reason_code.is_failure:
            client.subscribe(f"{TOPIC}/+/+", qos=1)

    @client.message_callback()
    def received(client, userdata, message):
        try:
            reading = Telemetry.model_validate_json(message.payload)
            if message.topic != f"{TOPIC}/{reading.run_id}/{reading.sensor_id}":
                raise ValueError("Telemetry envelope does not match its topic")
        except (ValidationError, ValueError):
            log.warning("Rejected malformed telemetry message")
        else:
            # Keep QoS 1 unacknowledged until the database transaction commits.
            while True:
                try:
                    store.insert(reading)
                    break
                except psycopg.OperationalError:
                    log.warning("Telemetry storage unavailable, retrying")
                    time.sleep(1)
        client.ack(message.mid, message.qos)

    client.connect(os.getenv("MQTT_HOST", "localhost"), int(os.getenv("MQTT_PORT", "1883")))
    client.loop_forever()


if __name__ == "__main__":
    consume()
