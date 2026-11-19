import pytest

from pipeline_twin.compression import compressor_metrics, optimize
from pipeline_twin.hydraulics import Pipeline, read_case


def test_power_and_temperature_reference():
    args = (300, 60, 0.017074024, 0.78, 1.30)
    assert compressor_metrics(4.5e6, 4.5e6, *args) == (0, 300)
    power, outlet = compressor_metrics(4.5e6, 6.5e6, *args)
    assert power == pytest.approx(4.313e6, rel=0.02)
    assert outlet == pytest.approx(334.1, abs=0.3)
    with pytest.raises(ValueError):
        compressor_metrics(6e6, 4e6, *args)


def test_optimized_delivery_and_infeasibility():
    pipe = Pipeline(read_case()["simulation"])
    result = optimize(pipe, duration_h=2)
    assert result["status"] == "feasible"
    assert result["optimized"]["delivery_pa_absolute"] >= 4.5e6
    assert result["optimized"]["power_w"] < result["baseline"]["power_w"]
    assert result["estimated_savings_kwh"] > 0
    assert optimize(pipe, delivery_min_pa=8e6)["status"] == "infeasible"
