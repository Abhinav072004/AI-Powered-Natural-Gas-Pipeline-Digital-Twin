from dataclasses import asdict

import pytest

from pipeline_twin.detection import Detector, Evidence, FeatureStream, LEAK
from pipeline_twin.simulation import simulate


def test_alert_persistence_and_gap():
    detector = Detector()
    leak = Evidence([1, 65, 60, 5, 6, 0, 0], 6, 4, 100, 1, None, 1e6)
    assert detector.classify(leak)["classification"] == "investigating imbalance"
    assert detector.classify(leak)["estimated_segment"] == 4
    assert detector.classify(leak)["classification"] == LEAK
    gap = Evidence([0], None, None, None, 0, None, None)
    assert detector.classify(gap)["classification"] == "communication fault"
    assert detector.classify(leak)["estimated_segment"] is None


def test_features_do_not_bridge_quality_gap():
    stream = FeatureStream()
    frames = list(simulate("normal", steps=8))
    for frame in frames[:3]:
        stamp = frame.readings[0].observed_at
        result = stream.update(stamp, [asdict(reading) for reading in frame.readings])
    assert result.residual_kg_s is not None
    resumed = frames[-1]
    stamp = resumed.readings[0].observed_at
    assert stream.update(stamp, [asdict(reading) for reading in resumed.readings]).residual_kg_s is None
    with pytest.raises(ValueError):
        stream.update(stamp, [])
