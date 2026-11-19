import json

from pipeline_twin.simulation import SCENARIOS, experiment, simulate


def test_seeded_sensor_output_and_faults():
    frames = list(simulate("small_leak", steps=16, seed=11))
    assert frames == list(simulate("small_leak", steps=16, seed=11))
    leaks = [frame for frame in frames if frame.event_active]
    assert leaks and len({frame.leak_segment for frame in leaks}) == 1
    assert all(frame.readings for frame in leaks)
    gap = list(simulate("communication_failure", steps=16))
    assert all(bool(frame.readings) != frame.event_active for frame in gap)
    fault = list(simulate("flow_fault", steps=16))
    assert any(r.quality == "missing" and r.value is None for frame in fault for r in frame.readings)


def test_chronological_episode_split(tmp_path):
    assert experiment(tmp_path, rounds=1, steps=12) == dict.fromkeys(("train", "validation", "test"), 10)
    last = None
    episodes = set()
    for split in ("train", "validation", "test"):
        rows = [json.loads(line) for line in (tmp_path / f"{split}.jsonl").read_text().splitlines()]
        assert len(rows) == 120
        assert {row["scenario"] for row in rows} == set(SCENARIOS)
        ids = {row["run_id"] for row in rows}
        assert len(ids) == 10 and not (ids & episodes)
        if last:
            assert rows[0]["observed_at"] > last
        last = rows[-1]["observed_at"]
        episodes.update(ids)
