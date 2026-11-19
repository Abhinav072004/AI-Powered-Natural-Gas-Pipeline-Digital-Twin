CREATE EXTENSION IF NOT EXISTS timescaledb;

CREATE TABLE IF NOT EXISTS telemetry (
    observed_at timestamptz NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now(),
    run_id text NOT NULL,
    message_id text NOT NULL,
    sensor_id text NOT NULL,
    envelope jsonb NOT NULL,
    PRIMARY KEY (observed_at, run_id, message_id)
);

SELECT create_hypertable('telemetry', 'observed_at', if_not_exists => TRUE);
CREATE INDEX IF NOT EXISTS telemetry_run_history ON telemetry (run_id, observed_at DESC);
CREATE INDEX IF NOT EXISTS telemetry_arrival ON telemetry (received_at DESC);

CREATE TABLE IF NOT EXISTS risk_review (
    review_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    reviewed_at timestamptz NOT NULL DEFAULT now(),
    hazard text NOT NULL,
    probability smallint NOT NULL CHECK (probability BETWEEN 1 AND 5),
    severity smallint NOT NULL CHECK (severity BETWEEN 1 AND 5),
    note text NOT NULL
);
