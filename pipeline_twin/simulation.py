"""Reproducible synthetic telemetry and chronologically separated experiment data."""

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import time
from typing import Iterator

import numpy as np

from .compression import compressor_metrics
from .hydraulics import Linepack, Pipeline, read_case

SCENARIOS = (
    "normal", "demand_increase", "pressure_drop", "large_leak", "small_leak",
    "pressure_drift", "flow_fault", "compressor_degradation", "communication_failure", "valve_abnormal",
)
LABELS = {
    "demand_increase": "demand fluctuation", "pressure_drop": "abnormal pressure event",
    "large_leak": "potential leakage", "small_leak": "potential leakage",
    "pressure_drift": "sensor malfunction", "flow_fault": "sensor malfunction",
    "compressor_degradation": "abnormal pressure event", "communication_failure": "communication fault",
    "valve_abnormal": "abnormal pressure event",
}


@dataclass(frozen=True)
class Reading:
    schema_version: int
    run_id: str
    message_id: str
    sensor_id: str
    segment_id: int
    boundary_index: int | None
    observed_at: str
    value: float | None
    unit: str
    quality: str


@dataclass(frozen=True)
class Frame:
    readings: list[Reading]
    scenario: str
    label: str
    leak_segment: int | None
    event_active: bool


def pressure_tag(index: int, final: int) -> str:
    if index == 0:
        return "PT-101"
    if index == final:
        return "PT-103"
    return "PT-102" if index == min(4, final - 1) else f"PT-B{index:02}"


def simulate(scenario: str, *, steps: int = 40, seed: int | None = None,
             start: datetime | None = None, run_id: str = "demo", settings: dict | None = None,
             interval_s: float | None = None) -> Iterator[Frame]:
    if scenario not in SCENARIOS or steps < 4:
        raise ValueError("Choose a known scenario and at least four samples")
    settings = read_case()["simulation"] if settings is None else settings
    pipe = Pipeline(settings)
    model = Linepack(pipe)
    rng = np.random.default_rng(settings["random_seed"] if seed is None else seed)
    start = start or datetime(2026, 1, 1, tzinfo=timezone.utc)
    interval = settings["sample_interval_s"] if interval_s is None else interval_s
    count = len(pipe.lengths)
    locations = settings["virtual_locations"]
    leak_index = int(rng.integers(count))
    inlet = settings["inlet_pressure_pa_absolute"] + rng.uniform(-6e4, 6e4)
    flow = settings["delivery_mass_flow_kg_s"] + rng.uniform(-3, 3)
    temperature = pipe.gas.temperature
    compressor = settings["compressor"]
    onset = steps // 3 + int(rng.integers(0, max(1, steps // 8)))
    base_wiggle = rng.uniform(0, 2 * np.pi)
    for step in range(steps):
        label = "normal operation"
        active = step >= onset and scenario != "normal"
        progress = min(1, (step - onset + 1) / 12) if active else 0
        p_in = inlet + 9000 * np.sin(step / 7 + base_wiggle)
        demand = flow + 0.55 * np.sin(step / 6 + base_wiggle)
        efficiency = compressor["isentropic_efficiency"]
        leak = np.zeros(count)
        if active:
            label = LABELS[scenario]
            if scenario == "demand_increase":
                demand += 11
            if scenario == "pressure_drop":
                p_in -= progress * 7e5
            if scenario in ("large_leak", "small_leak"):
                severity = rng.uniform(11, 13) if scenario == "large_leak" else rng.uniform(2.3, 3.2)
                leak[leak_index] = severity
            if scenario == "compressor_degradation":
                efficiency -= 0.20 * progress
        state = model.step(float(p_in), float(demand), interval, leak)
        observed_at = (start + timedelta(seconds=step * interval)).isoformat()
        readings = []

        def add(tag, boundary, value, unit, uncertainty=0.0, quality="good"):
            segment = min(max(1, boundary or 1), count)
            measured = float(value + rng.normal(0, uncertainty)) if value is not None else None
            readings.append(Reading(1, run_id, f"{step}:{tag}", tag, segment, boundary, observed_at,
                                    measured, unit, quality))

        # An interruption drops telemetry rather than transmitting misleading zeroes.
        if not (active and scenario == "communication_failure"):
            for idx in locations["pressure_and_temperature_station_boundaries"]:
                pressure = state.boundary_pressures_pa[idx]
                if active and scenario == "pressure_drift" and idx == min(4, count - 1):
                    pressure += progress * 3.5e5
                add(pressure_tag(idx, count), idx, pressure, "Pa(a)", 1500)
                add("TT-101" if idx == 0 else f"TT-B{idx:02}", idx, temperature, "K", 0.05)
            add("FT-101", 0, state.face_flows_kg_s[0], "kg/s", 0.14)
            missing = active and scenario == "flow_fault" and step % 5 == 0
            measured_flow = state.face_flows_kg_s[-1] - (4.0 if active and scenario == "flow_fault" else 0)
            add("FT-102", count, None if missing else measured_flow, "kg/s", 0.14,
                "missing" if missing else "good")
            if state.face_flows_kg_s[0] > 0:
                power, discharge = compressor_metrics(
                    compressor["suction_pressure_pa_absolute"], p_in, temperature, state.face_flows_kg_s[0],
                    pipe.gas.molecular_weight, efficiency, compressor["baseline_heat_capacity_ratio"],
                )
                add("TT-102", 0, discharge, "K", 0.18)
            else:
                # The fixed-pressure boundary allows reverse flow. There is no forward compression.
                power = 0.0
                add("TT-102", 0, None, "K", quality="missing")
            add("VIB-101", 0, 2.0 + (3.9 * progress if active and scenario == "compressor_degradation" else 0),
                "mm/s", 0.08)
            add("PWR-101", 0, power, "W", 8000 if power else 0)
            for ordinal, boundary in enumerate(locations["sectionalizing_valve_boundaries"]):
                add("XV-101" if ordinal == 0 else f"XV-B{boundary:02}", boundary,
                    int(not (ordinal == 0 and active and scenario == "valve_abnormal")), "boolean")
        yield Frame(readings, scenario, label, leak_index + 1 if active and np.any(leak) else None, active)


def experiment(output: Path, rounds: int = 2, steps: int = 32) -> dict[str, int]:
    if rounds < 1 or steps < 12:
        raise ValueError("Experiments need at least one round and twelve samples per episode")
    output.mkdir(parents=True, exist_ok=True)
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    settings = read_case()["simulation"]
    counts = {}
    for split_index, split in enumerate(("train", "validation", "test")):
        episode_count = 0
        with (output / f"{split}.jsonl").open("w") as handle:
            for iteration in range(rounds):
                for index, scenario in enumerate(SCENARIOS):
                    run_id = f"{split}-{iteration}-{index}"
                    seed = settings["random_seed"] + split_index * 100_000 + iteration * len(SCENARIOS) + index
                    for step, frame in enumerate(simulate(scenario, start=start, seed=seed, run_id=run_id, steps=steps)):
                        record = asdict(frame)
                        record.update(run_id=run_id, step=step,
                                      observed_at=(start + timedelta(seconds=step * settings["sample_interval_s"])).isoformat())
                        handle.write(json.dumps(record, allow_nan=False) + "\n")
                    start += timedelta(seconds=(steps + 1) * settings["sample_interval_s"])
                    episode_count += 1
        counts[split] = episode_count
    return counts


def export_csv(output: Path):
    """Flatten boundary instrumentation into a tabular file per split."""
    import pandas as pd

    columns_by_sensor = {
        "PT-101": "inlet_pressure_pa_absolute", "PT-103": "outlet_pressure_pa_absolute",
        "FT-101": "inlet_flow_kg_s", "FT-102": "outlet_flow_kg_s", "TT-101": "gas_temperature_k",
        "PWR-101": "compressor_power_w",
    }
    for split in ("train", "validation", "test"):
        with (output / f"{split}.jsonl").open() as dataset:
            frames = [json.loads(line) for line in dataset]
        rows = []
        for frame in frames:
            observations = {reading["sensor_id"]: reading for reading in frame["readings"]}
            health = ("unavailable" if not observations else
                      "degraded" if any(reading["quality"] != "good" for reading in observations.values()) else "good")
            rows.append({
                "timestamp": frame["observed_at"], "run_id": frame["run_id"], "step": frame["step"],
                "affected_segment_id": frame["leak_segment"], "sensor_health": health,
                "event_label": frame["label"], "scenario": frame["scenario"],
                **{column: observations.get(sensor, {}).get("value") for sensor, column in columns_by_sensor.items()},
            })
        pd.DataFrame(rows).to_csv(output / f"{split}.csv", index=False)


def publish(host: str, port: int, scenario: str, period_s: float, steps: int, run_id: str):
    import os
    import paho.mqtt.client as mqtt

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if username := os.getenv("MQTT_USERNAME"):
        client.username_pw_set(username, os.environ["MQTT_PASSWORD"])
    client.connect(host, port)
    client.loop_start()
    try:
        interval = read_case()["simulation"]["sample_interval_s"]
        start = datetime.now(timezone.utc) - timedelta(seconds=max(0, interval - period_s) * (steps - 1))
        for frame in simulate(scenario, steps=steps, start=start, run_id=run_id, interval_s=interval):
            pending = []
            for reading in frame.readings:
                topic = f"prototype/telemetry/v1/{run_id}/{reading.sensor_id}"
                message = client.publish(topic, json.dumps(asdict(reading), allow_nan=False), qos=1)
                pending.append((topic, message))
            for topic, message in pending:
                message.wait_for_publish(timeout=10)
                if not message.is_published():
                    raise RuntimeError(f"MQTT publish did not complete for {topic}")
            time.sleep(period_s)
    finally:
        client.disconnect()
        client.loop_stop()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    dataset = commands.add_parser("dataset")
    dataset.add_argument("--output", type=Path, default=Path("artifacts/data"))
    dataset.add_argument("--rounds", type=int, default=2)
    dataset.add_argument("--steps", type=int, default=32)
    dataset.add_argument("--csv", action="store_true", help="Also export flat frame data with Pandas")
    stream = commands.add_parser("publish")
    stream.add_argument("--host", default="localhost")
    stream.add_argument("--port", type=int, default=1883)
    stream.add_argument("--scenario", choices=SCENARIOS, default="normal")
    stream.add_argument("--period", type=float, default=60)
    stream.add_argument("--steps", type=int, default=40)
    stream.add_argument("--run-id", default=f"demo-{int(time.time())}")
    args = parser.parse_args()
    if args.command == "dataset":
        print(json.dumps(experiment(args.output, args.rounds, args.steps), indent=2))
        if args.csv:
            export_csv(args.output)
    else:
        if args.period <= 0:
            parser.error("publish --period must be positive")
        publish(args.host, args.port, args.scenario, args.period, args.steps, args.run_id)


if __name__ == "__main__":
    main()
