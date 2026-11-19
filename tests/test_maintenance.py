import joblib

from pipeline_twin.maintenance import assess, train


def test_failure_model_scores_rising_degradation(tmp_path):
    report = train(tmp_path)
    assert report["held_out_episodes"] == 40
    assert report["roc_auc"] > 0.9
    model = joblib.load(tmp_path / "maintenance.joblib")
    degraded = assess({"compressor": [0.5, 0.63, 0.71, 0.78, 0.86]}, model)[0]
    healthy = assess({"compressor": [0.07] * 5}, model)[0]
    assert degraded["failure_probability"] > healthy["failure_probability"]
    assert degraded["priority"] > healthy["priority"]
    assert degraded["health_score"] < healthy["health_score"]
    assert assess({})[0]["health_score"] is None
