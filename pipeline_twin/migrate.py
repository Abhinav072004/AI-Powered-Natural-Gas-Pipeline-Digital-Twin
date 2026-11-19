"""Apply the versioned idempotent schema to the configured TimescaleDB database."""

import os
from pathlib import Path

from .storage import Store


if __name__ == "__main__":
    path = Path(__file__).resolve().parents[1] / "deploy/schema.sql"
    with Store(os.environ["DATABASE_URL"]).connect() as connection:
        connection.execute(path.read_text())
