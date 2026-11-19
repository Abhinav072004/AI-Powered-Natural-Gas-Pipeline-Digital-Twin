from fastapi.testclient import TestClient
import pytest
from pydantic import ValidationError

from pipeline_twin.api import app
from pipeline_twin.storage import Telemetry

client = TestClient(app)


def test_dashboard_demo_and_missing_data():
    assert client.get("/healthz").status_code == 200
    response = client.get("/api/demo/normal")
    assert response.status_code == 200
    assert len(response.json()["segments"]) == 8
    meter = next(item for item in response.json()["maintenance"] if item["equipment"] == "flow meter")
    assert meter["health_score"] == 100
    response = client.get("/api/demo/communication_failure")
    assert response.json()["detection"]["classification"] == "communication fault"
    assert response.json()["average_pressure_pa"] is None
    assert client.get("/api/demo/unsupported").status_code == 404


def test_energy_risk_and_input_validation():
    assert client.get("/api/energy?delivery_bar=80").json()["status"] == "infeasible"
    payload = {"hazard": "equipment failure", "probability": 4, "severity": 5}
    assert client.post("/api/risk", json=payload).json()["level"] == "critical"
    assert client.post("/api/risk", json=dict(payload, severity=6)).status_code == 422


def test_telemetry_rejects_null_good_and_nonfinite_values():
    data = dict(schema_version=1, run_id="test", message_id="12:PT-101", sensor_id="PT-101", segment_id=1,
                boundary_index=0, observed_at="2026-01-01T00:00:00+00:00", value=6.5e6, unit="Pa(a)", quality="good")
    assert Telemetry.model_validate(data).value == 6.5e6
    for updated in (dict(value=None), dict(value=float("nan")), dict(unit="kg/s")):
        with pytest.raises(ValidationError):
            Telemetry.model_validate(dict(data, **updated))
