"""Dashboard API for synthetic telemetry, analysis, and decision support."""

from collections import defaultdict
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path
import os
from threading import Lock
from time import perf_counter

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
import joblib
import numpy as np
import psycopg
from pydantic import BaseModel, ConfigDict, Field

from .compression import optimize
from .detection import Detector, FeatureStream, NORMAL
from .hydraulics import Pipeline, read_case
from .maintenance import assess, condition_indicators
from . import risk
from .simulation import SCENARIOS, pressure_tag, simulate
from .storage import Store

settings = read_case()
risk_thresholds = risk.thresholds_from_config(settings["risk"])
pipe = Pipeline(settings["simulation"])
profile = [asdict(segment) for segment in pipe.steady()]
store = Store(os.getenv("DATABASE_URL"))
app = FastAPI(title="Pipeline Digital Twin", version="0.1.0")
if origins := os.getenv("CORS_ORIGINS"):
    app.add_middleware(CORSMiddleware, allow_origins=origins.split(","), allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])


@lru_cache(maxsize=2)
def model(name):
    path = Path(os.getenv("MODEL_DIRECTORY", "artifacts/models")) / f"{name}.joblib"
    return joblib.load(path) if path.exists() else None


def analyze(run_id: str | None, frames: list[dict], state: str) -> dict:
    stream = FeatureStream(pipe)
    detector = Detector(model("detection"))
    assessments = defaultdict(list)
    trend = []
    events = []
    latest = None
    inference_ms = 0.0
    for frame in frames:
        start = perf_counter()
        evidence = stream.update(frame["observed_at"], frame["readings"])
        latest = detector.classify(evidence)
        inference_ms = (perf_counter() - start) * 1000
        values = {r["sensor_id"]: r["value"] for r in frame["readings"] if r["quality"] == "good"}
        if latest["classification"] != NORMAL:
            events.append(dict(latest, observed_at=frame["observed_at"]))
        trend.append({"observed_at": frame["observed_at"], "inlet_pressure_pa": values.get("PT-101"),
                      "outlet_pressure_pa": values.get("PT-103"), "inlet_flow_kg_s": values.get("FT-101"),
                      "delivery_flow_kg_s": values.get("FT-102"), "power_w": values.get("PWR-101"),
                      **latest})
        indicators = condition_indicators(frame["readings"], evidence)
        for name, indicator in indicators.items():
            if indicator is not None:
                assessments[name].append(indicator)
            else:
                assessments[name].clear()
    latest_readings = frames[-1]["readings"] if frames and state != "stale" else []
    values = {r["sensor_id"]: r["value"] for r in latest_readings if r["quality"] == "good"}
    count = len(profile)
    observed = [values.get(pressure_tag(i, count)) for i in range(count + 1)]
    usable = [p for p in observed if p is not None]
    segments = [dict(segment, observed_inlet_pa=observed[index], observed_outlet_pa=observed[index + 1])
                for index, segment in enumerate(profile)]
    if state == "stale":
        latest = {"classification": "communication fault", "availability": 0.0}
        assessments.clear()
    return {
        "state": state, "run_id": run_id, "case_study": settings["case_study"],
        "observed_at": frames[-1]["observed_at"] if frames else None,
        "average_pressure_pa": float(np.mean(usable)) if usable else None,
        "latest_readings": latest_readings, "detection": latest,
        "segments": segments, "trends": trend, "events": events,
        "maintenance": assess(assessments, model("maintenance")),
        "inference_ms": round(inference_ms, 3),
        "model_loaded": model("detection") is not None,
        "scenario_names": SCENARIOS,
        "sample_interval_s": settings["simulation"]["sample_interval_s"],
    }


@app.get("/healthz")
def health():
    if store.url:
        try:
            store.check()
        except psycopg.Error as exc:
            raise HTTPException(503, "Telemetry database unavailable") from exc
    return {"status": "ok", "storage": "timescaledb" if store.url else "demo-only"}


@app.get("/api/dashboard")
def dashboard(run_id: str | None = Query(None, max_length=80)):
    try:
        run, frames, arrived = store.latest(run_id)
    except psycopg.Error as exc:
        raise HTTPException(503, "Telemetry database unavailable") from exc
    state = "waiting"
    if arrived:
        timeout = float(os.getenv("TELEMETRY_STALE_AFTER_S", "180"))
        state = "stale" if (datetime.now(timezone.utc) - arrived).total_seconds() > timeout else "live"
    return analyze(run, frames, state)


@lru_cache(maxsize=10)
def demo_payload(scenario: str):
    frames = []
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i, sample in enumerate(simulate(scenario, start=start, run_id=f"demo-{scenario}")):
        timestamp = start + timedelta(seconds=settings["simulation"]["sample_interval_s"] * i)
        frames.append({"observed_at": timestamp.isoformat(), "readings": [asdict(r) for r in sample.readings]})
    return analyze(f"demo-{scenario}", frames, "demo")


@app.get("/api/demo/{scenario}")
def demo(scenario: str):
    if scenario not in SCENARIOS:
        raise HTTPException(404, "Unknown synthetic scenario")
    return demo_payload(scenario)


@lru_cache(maxsize=32)
def energy_result(flow, delivery, hours):
    return optimize(pipe, flow, delivery, hours)


@app.get("/api/energy")
def energy(flow: float = Query(60, gt=0, le=200), delivery_bar: float = Query(45, gt=0, le=100),
           hours: float = Query(1, gt=0, le=720)):
    return energy_result(flow, delivery_bar * 1e5, hours)


class RiskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hazard: str
    probability: int = Field(ge=1, le=5)
    severity: int = Field(ge=1, le=5)
    note: str = Field(default="", max_length=1000)
    save: bool = False


@app.get("/api/risk")
def risk_matrix():
    return {"hazards": sorted(risk.HAZARDS),
            "matrix": [[risk.assess("potential leakage", p, s, risk_thresholds) for s in range(1, 6)] for p in range(1, 6)]}


@app.post("/api/risk")
def evaluate_risk(request: RiskRequest):
    try:
        assessment = risk.assess(request.hazard, request.probability, request.severity, risk_thresholds)
        if request.save:
            if not store.url:
                raise HTTPException(503, "Review storage is unavailable in demo-only mode")
            assessment = store.save_review(assessment, request.note)
        return assessment
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except psycopg.Error as exc:
        raise HTTPException(503, "Review storage unavailable") from exc


class CopilotRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    question: str = Field(min_length=5, max_length=1000)
    scenario: str | None = None


knowledge_index_lock = Lock()


@lru_cache(maxsize=1)
def load_knowledge_index():
    from .copilot import KnowledgeIndex, passages
    directory = os.getenv("KNOWLEDGE_PDF_DIRECTORY")
    return KnowledgeIndex(passages(Path(directory) if directory else None), os.getenv("KNOWLEDGE_INDEX_PATH"))


@app.post("/api/copilot")
def copilot(request: CopilotRequest):
    from .copilot import answer

    if request.scenario is not None and request.scenario not in SCENARIOS:
        raise HTTPException(422, "Unknown synthetic scenario")
    snapshot = demo_payload(request.scenario) if request.scenario else dashboard()
    context = None
    if snapshot["observed_at"]:
        detection = snapshot["detection"] or {}
        pressure = snapshot["average_pressure_pa"]
        pressure_text = f"{pressure / 1e5:.2f} bar(a)" if pressure is not None else "unavailable"
        context = (f"Simulated run {snapshot['run_id']} at {snapshot['observed_at']}, "
                   f"state {snapshot['state']}. Average pressure {pressure_text}. Classification "
                   f"{detection.get('classification', 'unavailable')}.")
        if detection.get("estimated_segment"):
            context += f" Candidate affected segment {detection['estimated_segment']}."
        if detection.get("residual_kg_s") is not None:
            context += f" Mass residual {detection['residual_kg_s']:.2f} kg/s."
    # Parallel first requests otherwise open the same persistent Chroma client together.
    with knowledge_index_lock:
        index = load_knowledge_index()
    return answer(index, request.question, context)
