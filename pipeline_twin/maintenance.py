"""Failure-window scoring trained on synthetic degradation trajectories."""

import argparse
import json
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, brier_score_loss, roc_auc_score
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

HORIZON_SAMPLES = 10
EQUIPMENT = {
    "compressor": (5, 5, "Review vibration, discharge temperature, and compression efficiency."),
    "sectionalizing valve": (5, 4, "Compare indication history with the approved inspection record."),
    "pressure transmitter": (4, 4, "Compare the reading with neighboring transmitters and review calibration."),
    "flow meter": (4, 4, "Check signal integrity, consistency with inventory, and calibration history."),
    "temperature sensor": (3, 3, "Check the signal against adjacent sensors and review calibration."),
}


def degradation_episodes(seed: int, count: int):
    rng = np.random.default_rng(seed)
    for _ in range(count):
        steps = np.arange(65)
        start = int(rng.integers(10, 28))
        rate = rng.uniform(0.01, 0.05) if rng.random() < 0.8 else 0
        latent = np.maximum(0, steps - start) * rate
        signal = np.maximum(0, latent + rng.normal(0, 0.05, len(steps)))
        for i in range(4, len(steps) - HORIZON_SAMPLES):
            if latent[i] < 1:
                yield signal[i-4:i+1], int(latent[i+HORIZON_SAMPLES] >= 1)


def feature_row(recent):
    recent = np.asarray(recent)
    return [float(recent[-1]), float((recent[-1] - recent[0]) / max(1, len(recent) - 1)),
            float(np.mean(recent > 0.60))]


def train(output: Path):
    training = list(degradation_episodes(142, 120))
    test = list(degradation_episodes(314, 40))
    model = make_pipeline(StandardScaler(), LogisticRegression(max_iter=500, random_state=42))
    model.fit([feature_row(signal) for signal, _ in training], [target for _, target in training])
    y = [target for _, target in test]
    scores = model.predict_proba([feature_row(signal) for signal, _ in test])[:, 1]
    report = {
        "training_episodes": 120, "held_out_episodes": 40, "evaluated_windows": len(test),
        "failure_horizon_samples": HORIZON_SAMPLES, "roc_auc": roc_auc_score(y, scores),
        "average_precision": average_precision_score(y, scores), "brier_score": brier_score_loss(y, scores),
    }
    output.mkdir(parents=True, exist_ok=True)
    joblib.dump(model, output / "maintenance.joblib")
    (output / "maintenance-evaluation.json").write_text(json.dumps(report, indent=2) + "\n")
    return report


def condition_indicators(readings: list[dict], evidence) -> dict[str, float | None]:
    values = {row["sensor_id"]: row["value"] for row in readings if row["quality"] == "good"}
    vibration, discharge = values.get("VIB-101"), values.get("TT-102")
    temp_reference = evidence.baseline_discharge_temperature_k
    compressor = (max(0, (vibration - 2) / 4, (discharge - temp_reference) / 14)
                  if vibration is not None and discharge is not None and temp_reference is not None else None)
    valve = values.get("XV-101")
    delivery_meter = next((reading for reading in readings if reading["sensor_id"] == "FT-102"), None)
    pressure, gradient_peer = evidence.features[7:9]
    temperature = values.get("TT-101")
    neighboring = [v for tag, v in values.items() if tag.startswith("TT-B") and v is not None]
    return {
        "compressor": compressor,
        "sectionalizing valve": 1.0 - valve if valve is not None else None,
        "pressure transmitter": (max(0.0, min(pressure, gradient_peer) - 15_000) / 160_000
                                 if np.isfinite(pressure) and np.isfinite(gradient_peer) else None),
        # Pipeline imbalance has multiple causes. Use direct meter quality for its condition indicator.
        "flow meter": float(delivery_meter["quality"] != "good") if delivery_meter is not None else None,
        "temperature sensor": (abs(temperature - float(np.median(neighboring))) / 3
                               if temperature is not None and neighboring else None),
    }


def assess(history: dict[str, list[float]], model=None) -> list[dict]:
    results = []
    for name, (consequence, criticality, inspection) in EQUIPMENT.items():
        readings = history.get(name, [])[-5:]
        if not readings:
            results.append({"equipment": name, "health_score": None, "priority": None,
                            "failure_probability": None, "inspection": "Check telemetry availability.",
                            "indicator_trend": []})
            continue
        indicator, _, frequency = feature_row(readings)
        probability = float(model.predict_proba([feature_row(readings)])[0, 1]) if model else None
        health = 100 * (1 - min(1, indicator))
        priority = (100 * (0.40 * probability + 0.20 * consequence / 5
                            + 0.20 * criticality / 5 + 0.20 * frequency)
                    if probability is not None else None)
        results.append({"equipment": name, "health_score": health, "priority": priority,
                        "failure_probability": probability, "inspection": inspection,
                        "indicator_trend": readings, "failure_horizon_samples": HORIZON_SAMPLES})
    return sorted(results, key=lambda row: row["priority"] if row["priority"] is not None else -1, reverse=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("artifacts/models"))
    args = parser.parse_args()
    print(json.dumps(train(args.output), indent=2))
