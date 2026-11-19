import numpy as np
import pytest

from pipeline_twin.hydraulics import Gas, GasProperties, Linepack, Pipeline, read_case


@pytest.fixture
def pipe():
    return Pipeline(read_case()["simulation"])


def test_methane_reference_and_invalid_state():
    methane = Gas({"methane": 1}, 300)
    props = methane.at(5e6)
    assert props.compressibility == pytest.approx(0.90177, abs=0.0002)
    assert props.density_kg_m3 == pytest.approx(35.66, abs=0.05)
    assert 1e-5 < props.viscosity_pa_s < 2e-5
    with pytest.raises(ValueError):
        methane.at(0)


def test_zero_flow_inventory(pipe):
    segments = pipe.steady(flow_kg_s=0)
    expected = pipe.gas.at(6.5e6).density_kg_m3 * sum(pipe.volumes)
    assert sum(s.inventory_kg for s in segments) == pytest.approx(expected)
    assert all(s.pressure_drop_pa == 0 and s.velocity_m_s == 0 for s in segments)


def test_constant_property_pressure_squared(pipe, monkeypatch):
    gas = pipe.gas
    def properties(pressure):
        return GasProperties(0.017074, 0.9, pressure * 0.017074 / (0.9 * 8.314462618 * 300), 1.2e-5)
    monkeypatch.setattr(gas, "at", properties)
    monkeypatch.setattr("pipeline_twin.hydraulics.friction_factor", lambda *_: 0.012)
    segments = pipe.steady()
    assert segments[-1].outlet_pressure_pa_absolute / 1e5 == pytest.approx(56.12, abs=0.01)


def test_convergence_and_sensitivity(pipe):
    normal = pipe.steady()
    refined = pipe.steady(tolerance=1e-10)
    higher = pipe.steady(flow_kg_s=70)
    assert all(s.pressure_drop_pa > 0 for s in normal)
    assert higher[-1].outlet_pressure_pa_absolute < normal[-1].outlet_pressure_pa_absolute
    assert normal[-1].outlet_pressure_pa_absolute == pytest.approx(refined[-1].outlet_pressure_pa_absolute, rel=1e-6)
    assert sum(s.inventory_kg for s in normal) == pytest.approx(sum(s.inventory_kg for s in refined), rel=1e-6)


def test_linepack_equilibrium_and_disturbance_conservation(pipe):
    model = Linepack(pipe)
    before = model.step(6.5e6, 60, 60)
    assert before.boundary_pressures_pa == pytest.approx(model.baseline.boundary_pressures_pa)
    assert before.face_flows_kg_s == pytest.approx([60] * 9)
    after = model.step(6.5e6, 70, 60, [0, 0, 0, 5, 0, 0, 0, 0])
    accumulated = after.inventory_kg - before.inventory_kg
    expected = 60 * (after.face_flows_kg_s[:-1] - after.face_flows_kg_s[1:] - after.leaks_kg_s)
    assert accumulated == pytest.approx(expected, abs=0.001)
    assert sum(accumulated) < 0
