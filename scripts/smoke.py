"""Check the built dashboard and API. Optionally verify a known MQTT replay run."""

import argparse
from datetime import datetime, timezone
import json
from time import monotonic, sleep
from urllib.parse import urlencode
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8080")
    parser.add_argument("--run-id", help="MQTT run to verify")
    parser.add_argument("--expect-stale", action="store_true", help="Wait for the same MQTT run to expire")
    args = parser.parse_args()
    if args.expect_stale and not args.run_id:
        parser.error("--expect-stale requires --run-id")

    def fetch(path, payload=None):
        headers = {"Content-Type": "application/json"} if payload is not None else {}
        body = json.dumps(payload).encode() if payload is not None else None
        with urlopen(Request(args.base_url.rstrip("/") + path, headers=headers, data=body), timeout=25) as response:
            return response.read()

    def read(path, payload=None):
        return json.loads(fetch(path, payload))

    assert b"Pipeline Digital Twin" in fetch("/")
    assert read("/healthz") == {"status": "ok", "storage": "timescaledb"}
    normal = read("/api/demo/normal")
    assert normal["state"] == "demo" and normal["model_loaded"]
    assert len(normal["segments"]) == 8 and normal["average_pressure_pa"] > 0
    assert normal["maintenance"][0]["failure_probability"] is not None
    missing = read("/api/demo/communication_failure")
    assert missing["detection"]["classification"] == "communication fault"
    assert missing["average_pressure_pa"] is None and not missing["latest_readings"]
    leak = read("/api/demo/large_leak")
    assert any(event["estimated_segment"] for event in leak["events"])
    energy = read("/api/energy")
    assert energy["status"] == "feasible" and energy["estimated_savings_kwh"] > 0
    assert energy["optimized"]["delivery_pa_absolute"] >= energy["delivery_min_pa_absolute"]
    assert read("/api/energy?delivery_bar=80")["status"] == "infeasible"
    review = read("/api/risk", {"hazard": "equipment failure", "probability": 5, "severity": 4,
                               "note": "Automated academic demo smoke test", "save": True})
    assert review["level"] == "critical" and review["review_id"] > 0
    copilot = read("/api/copilot", {"question": "What is linepack?", "scenario": "normal"})
    assert copilot["sources"] and "[1]" in copilot["answer"]
    assert "Simulated run demo-normal" in copilot["simulated_context"]
    print(f"PASS: dashboard, analytics, faults, TimescaleDB risk review and cited copilot. "
          f"Normal replay inference {normal['inference_ms']:.2f} ms for latest frame.")

    if args.run_id:
        path = "/api/dashboard?" + urlencode({"run_id": args.run_id})
        deadline = monotonic() + 15
        while monotonic() < deadline:
            streaming = read(path)
            if streaming["state"] == "live" and len(streaming["trends"]) >= 6:
                break
            sleep(0.5)
        else:
            raise AssertionError("MQTT readings did not reach the dashboard API")
        stamps = [datetime.fromisoformat(point["observed_at"]) for point in streaming["trends"]]
        assert streaming["run_id"] == args.run_id and stamps == sorted(set(stamps))
        assert stamps[-1] <= datetime.now(timezone.utc)
        assert streaming["latest_readings"]
        print(f"PASS: MQTT → TimescaleDB → FastAPI for {args.run_id} with {len(stamps)} intervals.")

        if args.expect_stale:
            deadline = monotonic() + 45
            while monotonic() < deadline:
                stale = read(path)
                if stale["state"] == "stale":
                    assert stale["detection"]["classification"] == "communication fault"
                    assert not stale["latest_readings"]
                    print("PASS: stopped stream transitions to stale with pressure and flow unavailable.")
                    break
                sleep(1)
            else:
                raise AssertionError("Stopped stream did not become stale")


if __name__ == "__main__":
    main()
