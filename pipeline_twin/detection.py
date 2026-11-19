"""Causal telemetry features, physics-based localization, and synthetic model evaluation."""

import argparse
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.metrics import classification_report, confusion_matrix, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler
from sklearn.svm import SVC

from .hydraulics import Linepack, Pipeline, read_case
from .simulation import pressure_tag

NORMAL = "normal operation"
LEAK = "potential leakage"
FAULT = "communication fault"
LABELS = (NORMAL, LEAK, "sensor malfunction", "demand fluctuation", "abnormal pressure event", FAULT)
FEATURE_SCHEMA_VERSION = 1


@dataclass
class Evidence:
    features: list[float]
    residual_kg_s: float | None
    worst_segment: int | None
    pressure_deviation_pa: float | None
    availability: float
    baseline_discharge_temperature_k: float | None
    estimated_inventory_kg: float | None


class FeatureStream:
    def __init__(self, pipe: Pipeline | None = None):
        self.pipe = pipe or Pipeline(read_case()["simulation"])
        self.baseline = Linepack(self.pipe).baseline
        pressure = self.baseline.boundary_pressures_pa
        self.resistance = (pressure[:-1]**2 - pressure[1:]**2) / self.baseline.face_flows_kg_s[0]**2
        self.history = deque(maxlen=5)
        self.flow_changes = deque(maxlen=5)
        self.last_seen = None
        self.last_pressure = None
        self.last_outflow = None

    def update(self, timestamp: str, readings: list[dict]) -> Evidence:
        elapsed_time = datetime.fromisoformat(timestamp).timestamp()
        if self.last_seen is not None and elapsed_time <= self.last_seen:
            raise ValueError("Feature stream requires strictly increasing observation timestamps")
        max_gap = self.pipe.settings["sample_interval_s"] * 1.6
        if self.last_seen is not None and elapsed_time - self.last_seen > max_gap:
            self.history.clear()
            self.flow_changes.clear()
            self.last_pressure = self.last_outflow = None
        self.last_seen = elapsed_time
        values = {row["sensor_id"]: row["value"] for row in readings
                  if row["quality"] == "good" and row["value"] is not None}
        count = len(self.pipe.lengths)
        pressures = np.array([values.get(pressure_tag(i, count), np.nan) for i in range(count + 1)])
        fi, fo = (values.get(tag, np.nan) for tag in ("FT-101", "FT-102"))
        vibration = values.get("VIB-101", np.nan)
        discharge = values.get("TT-102", np.nan)
        valve = values.get("XV-101", np.nan)
        good_pressures = np.isfinite(pressures).all() and ((1e5 <= pressures) & (pressures <= 1e7)).all()
        complete = bool(good_pressures and np.isfinite(fi) and np.isfinite(fo) and "TT-101" in values)
        availability = float((np.isfinite(pressures).sum() + np.isfinite(fi) + np.isfinite(fo)) / (count + 3))
        max_gradient = second_gradient = min_flow_change = np.nan
        residual = deviation = inventory = baseline_discharge = None
        location = None
        if complete:
            # Temperature-correct each density from its local observation using the isothermal EOS value.
            # The correction is first-order in temperature and avoids refitting the entire EOS to sensor noise.
            temperatures = np.array([values.get("TT-101" if i == 0 else f"TT-B{i:02}", np.nan)
                                     for i in range(count + 1)])
            if np.isfinite(temperatures).all() and ((275 <= temperatures) & (temperatures <= 340)).all():
                densities = np.array([self.pipe.gas.at(p).density_kg_m3 for p in pressures])
                densities *= self.pipe.gas.temperature / temperatures
                inventory = float(np.dot(self.pipe.volumes, (densities[:-1] + densities[1:]) / 2))
                self.history.append((elapsed_time, inventory, float(fi - fo)))
                if len(self.history) >= 3:
                    times, masses, imbalances = map(np.asarray, zip(*self.history))
                    durations = np.diff(times)
                    integrated = float(np.dot(durations, (imbalances[:-1] + imbalances[1:]) / 2))
                    residual = (integrated - (masses[-1] - masses[0])) / (times[-1] - times[0])
            else:
                self.history.clear()
            squares = pressures[:-1]**2 - pressures[1:]**2
            inferred = np.sign(squares) * np.sqrt(np.abs(squares) / self.resistance)
            # Each inferred segment flow approximates a center value. Compare its
            # upstream and downstream face neighborhoods to rank affected segments.
            adjacent = np.r_[fi, inferred, fo]
            discontinuity = adjacent[:-2] - adjacent[2:]
            location = int(np.argmax(discontinuity)) + 1
            min_flow_change = float(np.max(discontinuity))
            expected = self.resistance * ((fi + fo) / 2)**2
            gradients = np.abs(squares - expected) / (pressures[:-1] + pressures[1:])
            max_gradient = float(np.max(gradients))
            second_gradient = float(np.partition(gradients, -2)[-2]) if count > 1 else 0.0
            predicted_out = max(0, pressures[0]**2 - sum(expected))**0.5
            deviation = float(pressures[-1] - predicted_out)
            comp = self.pipe.settings["compressor"]
            if pressures[0] >= comp["suction_pressure_pa_absolute"]:
                from .compression import compressor_metrics
                _, baseline_discharge = compressor_metrics(
                    comp["suction_pressure_pa_absolute"], pressures[0], values["TT-101"], max(0, fi),
                    self.pipe.gas.molecular_weight, comp["isentropic_efficiency"], comp["baseline_heat_capacity_ratio"],
                )
        else:
            self.history.clear()
        dp = pressures[0] - self.last_pressure if self.last_pressure is not None else np.nan
        dq = fo - self.last_outflow if self.last_outflow is not None else np.nan
        self.last_pressure = pressures[0] if np.isfinite(pressures[0]) else None
        self.last_outflow = fo if np.isfinite(fo) else None
        if np.isfinite(dq):
            self.flow_changes.append(float(dq))
        recent_flow_change = max(self.flow_changes, default=np.nan)
        return Evidence([
            availability, fi, fo, fi - fo, residual if residual is not None else np.nan, dp,
            recent_flow_change, max_gradient, second_gradient, min_flow_change, pressures[0],
            pressures[-1], vibration, discharge, valve,
        ], residual, location, deviation, availability, baseline_discharge, inventory)


def physics_predict(evidence: Evidence) -> str:
    if evidence.availability == 0:
        return FAULT
    if evidence.availability < 1:
        return "sensor malfunction"
    if evidence.residual_kg_s is not None and evidence.residual_kg_s > 3 and evidence.features[3] > 1.5:
        return LEAK
    if evidence.features[6] > 3:
        return "demand fluctuation"
    if evidence.features[5] < -2e4:
        return "abnormal pressure event"
    return NORMAL


class Detector:
    def __init__(self, artifact: dict | None = None):
        if artifact is not None and artifact.get("feature_version") != FEATURE_SCHEMA_VERSION:
            raise ValueError("Incompatible detection model artifact")
        self.artifact = artifact
        self.candidates = deque(maxlen=3)

    def classify(self, evidence: Evidence, scores: dict | None = None, novelty: float | None = None) -> dict:
        candidate = physics_predict(evidence)
        probability = None
        if self.artifact and evidence.availability > 0:
            if scores is None:
                features = np.array([evidence.features])
                model = self.artifact["classifier"]
                scores = dict(zip(model.classes_, model.predict_proba(features)[0]))
                novelty = float(-self.artifact["novelty"].decision_function(features)[0])
            probability = float(scores.get(LEAK, 0))
            if evidence.availability == 1:
                candidate = max((label for label in scores if label != LEAK), key=scores.get, default=NORMAL)
                if probability >= self.artifact["threshold"] and (
                    evidence.residual_kg_s is not None and evidence.residual_kg_s > 0
                ):
                    candidate = LEAK
        if evidence.availability == 0:
            novelty = None
        self.candidates.append(evidence.worst_segment if candidate == LEAK else None)
        persistent = (candidate == LEAK and len(self.candidates) >= 2
                      and self.candidates[-1] is not None and self.candidates[-2] is not None)
        label = candidate if candidate != LEAK or persistent else "investigating imbalance"
        return {
            "classification": label, "leak_probability": probability, "novelty_score": novelty,
            "estimated_segment": evidence.worst_segment if persistent else None,
            "residual_kg_s": evidence.residual_kg_s, "availability": evidence.availability,
            "pressure_deviation_pa": evidence.pressure_deviation_pa,
            "observed_inventory_kg": evidence.estimated_inventory_kg,
        }


def data(path: Path):
    rows = []
    previous = None
    pipe = Pipeline(read_case()["simulation"])
    with path.open() as handle:
        for line in handle:
            row = json.loads(line)
            if row["run_id"] != previous:
                stream = FeatureStream(pipe)
                previous = row["run_id"]
            evidence = stream.update(row["observed_at"], row["readings"])
            rows.append((row, evidence))
    return rows


def replay(rows, artifact):
    previous = None
    outputs = []
    scores = [None] * len(rows)
    novelty = [None] * len(rows)
    if artifact and rows:
        features = np.array([evidence.features for _, evidence in rows])
        classifier = artifact["classifier"]
        scores = [dict(zip(classifier.classes_, values)) for values in classifier.predict_proba(features)]
        novelty = (-artifact["novelty"].decision_function(features)).tolist()
    for (row, evidence), probabilities, anomaly in zip(rows, scores, novelty):
        if previous != row["run_id"]:
            detector = Detector(artifact)
            previous = row["run_id"]
        outputs.append(detector.classify(evidence, probabilities, anomaly))
    return outputs


def evaluate(rows, outputs):
    truth = [row["label"] for row, _ in rows]
    predictions = [o["classification"] if o["classification"] in LABELS else NORMAL for o in outputs]
    scores = [o["leak_probability"] for o in outputs]
    all_probability = any(score is not None for score in scores)
    normal_count = truth.count(NORMAL)
    false_alarms = sum(actual == NORMAL and predicted == LEAK for actual, predicted in zip(truth, predictions))
    false_alarm_events = 0
    previous_false_alarm_run = None
    novelty_samples = []
    event_runs = {}
    errors = defaultdict(list)
    false_positive_scenarios = Counter()
    missed_samples_by_scenario = Counter()
    bounds = read_case()["simulation"]["segment_boundaries_km"]
    centers = [(a + b) / 2 for a, b in zip(bounds, bounds[1:])]
    for (row, _), out in zip(rows, outputs):
        false_alarm = row["label"] == NORMAL and out["classification"] == LEAK
        if false_alarm and previous_false_alarm_run != row["run_id"]:
            false_alarm_events += 1
        previous_false_alarm_run = row["run_id"] if false_alarm else None
        if out["novelty_score"] is not None:
            novelty_samples.append((row["label"] != NORMAL, out["novelty_score"]))
        if row["label"] != LEAK and out["classification"] == LEAK:
            false_positive_scenarios[row["scenario"]] += 1
        if row["leak_segment"] is not None:
            if out["classification"] != LEAK:
                missed_samples_by_scenario[row["scenario"]] += 1
            episode = event_runs.setdefault(row["run_id"], (row["step"], None))
            if out["estimated_segment"] is not None:
                if episode[1] is None:
                    event_runs[row["run_id"]] = (episode[0], row["step"])
                errors[row["scenario"]].append(abs(centers[row["leak_segment"] - 1]
                                                  - centers[out["estimated_segment"] - 1]))
    interval = read_case()["simulation"]["sample_interval_s"]
    latency = [(end - start) * interval for start, end in event_runs.values() if end is not None]
    result = classification_report(truth, predictions, labels=list(LABELS), output_dict=True, zero_division=0)
    novelty_labels, novelty_scores = zip(*novelty_samples) if novelty_samples else ([], [])
    localization = [error for samples in errors.values() for error in samples]
    return {
        "false_positive_samples_by_scenario": dict(false_positive_scenarios),
        "false_negative_samples_by_leak_size": dict(missed_samples_by_scenario),
        "localization_by_leak_size": {
            name: {"samples": len(samples), "mean_error_km": float(np.mean(samples)),
                   "exact_segment_fraction": samples.count(0) / len(samples)}
            for name, samples in errors.items()
        },
        "isolation_forest_novelty_roc_auc": roc_auc_score(novelty_labels, novelty_scores)
        if len(set(novelty_labels)) == 2 else None,
        "classification": result, "labels": LABELS,
        "confusion_matrix": confusion_matrix(truth, predictions, labels=LABELS).tolist(),
        "leak_roc_auc": roc_auc_score([label == LEAK for label in truth], [score or 0 for score in scores])
        if all_probability else None,
        "false_leak_alarm_fraction_of_normal_samples": false_alarms / normal_count,
        "false_leak_alarms_per_normal_hour": false_alarm_events / (normal_count * interval / 3600),
        "leak_episodes": len(event_runs), "missed_episodes": len(event_runs) - len(latency),
        "median_detection_latency_s": float(np.median(latency)) if latency else None,
        "localized_samples": len(localization),
        "mean_localization_error_km": float(np.mean(localization)) if localization else None,
        "exact_segment_fraction": localization.count(0) / len(localization) if localization else None,
    }


def train(directory: Path, output: Path, include_xgboost: bool = False):
    train_rows, validation, test = (data(directory / f"{split}.jsonl") for split in ("train", "validation", "test"))
    x = np.array([e.features for _, e in train_rows])
    y = np.array([row["label"] for row, _ in train_rows])
    # Complete normal windows only. Missing values in an inference window use the fitted median.
    novelty = make_pipeline(SimpleImputer(strategy="median"), IsolationForest(random_state=42, n_estimators=80))
    novelty.fit(x[y == NORMAL])
    models = {
        "random_forest": RandomForestClassifier(n_estimators=110, min_samples_leaf=3, class_weight="balanced", random_state=42),
        "svm": make_pipeline(SimpleImputer(strategy="median"), StandardScaler(),
                             SVC(probability=True, class_weight="balanced", random_state=42)),
    }
    if include_xgboost:
        from xgboost import XGBClassifier
        models["xgboost"] = XGBClassifier(n_estimators=80, random_state=42, n_jobs=2)
    report = {"physics": evaluate(test, replay(test, None))}
    candidates = []
    for name, model in models.items():
        if name == "xgboost":
            from pipeline_twin.detection import EncodedClassifier
            from sklearn.preprocessing import LabelEncoder
            model = EncodedClassifier(model, LabelEncoder())
        model.fit(x, y)
        artifact = {"classifier": model, "novelty": novelty, "feature_version": FEATURE_SCHEMA_VERSION}
        rankings = []
        for threshold in (0.25, 0.40, 0.55, 0.70):
            candidate = dict(artifact, threshold=threshold)
            validation_result = evaluate(validation, replay(validation, candidate))
            leak = validation_result["classification"][LEAK]
            fpr = validation_result["false_leak_alarm_fraction_of_normal_samples"]
            rankings.append(((fpr <= 0.05, leak["recall"], leak["precision"], -fpr), candidate))
        score, candidate = max(rankings, key=lambda item: item[0])
        report[name] = dict(evaluate(test, replay(test, candidate)), validation_threshold=candidate["threshold"])
        candidates.append((score, name, candidate))
    _, selected, artifact = max(candidates, key=lambda item: item[0])
    report["selected"] = selected
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(artifact, output / "detection.joblib")
    (output / "evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


class EncodedClassifier:
    def __init__(self, model, encoder):
        self.model = model
        self.encoder = encoder

    def fit(self, features, labels):
        self.model.fit(features, self.encoder.fit_transform(labels))
        self.classes_ = self.encoder.classes_

    def predict_proba(self, features):
        return self.model.predict_proba(features)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, default=Path("artifacts/data"))
    parser.add_argument("--output", type=Path, default=Path("artifacts/models"))
    parser.add_argument("--xgboost", action="store_true")
    args = parser.parse_args()
    print(json.dumps(train(args.data, args.output, args.xgboost), indent=2))
