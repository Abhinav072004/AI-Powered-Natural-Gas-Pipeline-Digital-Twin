"""Constant-heat-capacity compressor approximation."""

from math import isfinite

from .hydraulics import R


def compressor_metrics(suction_pa: float, discharge_pa: float, suction_k: float, mass_flow_kg_s: float,
                       molecular_weight_kg_mol: float, efficiency: float, heat_capacity_ratio: float) -> tuple[float, float]:
    inputs = (suction_pa, discharge_pa, suction_k, mass_flow_kg_s, molecular_weight_kg_mol,
              efficiency, heat_capacity_ratio)
    if not all(map(isfinite, inputs)) or not (
        0 < suction_pa <= discharge_pa and 0 < suction_k and 0 <= mass_flow_kg_s
        and 0 < molecular_weight_kg_mol and 0 < efficiency <= 1 and 1 < heat_capacity_ratio
    ):
        raise ValueError("Invalid compressor pressure ratio, flow, gas properties or efficiency")
    exponent = (heat_capacity_ratio - 1) / heat_capacity_ratio
    delta_t = suction_k * ((discharge_pa / suction_pa)**exponent - 1) / efficiency
    cp = R / (molecular_weight_kg_mol * exponent)
    return mass_flow_kg_s * cp * delta_t, suction_k + delta_t


def optimize(pipe, flow_kg_s: float | None = None, delivery_min_pa: float | None = None,
             duration_h: float = 1) -> dict:
    """Find the minimum feasible discharge pressure at fixed simulated delivery."""
    from functools import lru_cache
    from scipy.optimize import brentq

    settings = pipe.settings
    config = settings["compressor"]
    flow = settings["delivery_mass_flow_kg_s"] if flow_kg_s is None else flow_kg_s
    delivery = config["minimum_delivery_pressure_pa_absolute"] if delivery_min_pa is None else delivery_min_pa
    suction = config["suction_pressure_pa_absolute"]
    upper = config["maximum_discharge_pressure_pa_absolute"]
    baseline_p = settings["inlet_pressure_pa_absolute"]
    if not all(map(isfinite, (flow, delivery, duration_h, suction, upper, baseline_p))) or not (
        flow > 0 and delivery > 0 and duration_h > 0 and 1e5 <= suction <= baseline_p <= upper <= 1e7
    ):
        raise ValueError("Invalid flow, delivery target, duration or configured pressure limits")

    @lru_cache
    def evaluate(discharge):
        try:
            outlet = pipe.steady(discharge, flow)[-1].outlet_pressure_pa_absolute
        except ValueError:
            return None
        power, _ = compressor_metrics(
            suction, discharge, pipe.gas.temperature, flow, pipe.gas.molecular_weight,
            config["isentropic_efficiency"], config["baseline_heat_capacity_ratio"],
        )
        return {"discharge_pa_absolute": discharge, "delivery_pa_absolute": outlet, "power_w": power}

    def margin(pressure):
        case = evaluate(pressure)
        return case["delivery_pa_absolute"] - delivery if case else -delivery

    baseline = evaluate(baseline_p)
    result = {"flow_kg_s": flow, "delivery_min_pa_absolute": delivery, "duration_h": duration_h,
              "baseline": baseline, "baseline_meets_delivery": margin(baseline_p) >= 0,
              "optimized": None, "estimated_savings_kwh": None}
    if margin(upper) < 0:
        return dict(result, status="infeasible")
    # At fixed flow the steady outlet is monotonic in inlet pressure and power is monotonic in pressure ratio.
    if margin(suction) >= 0:
        candidate = suction
    else:
        candidate = min(upper, brentq(margin, suction, upper, xtol=0.1) + 0.1)
    optimized = evaluate(candidate)
    if optimized is None or optimized["delivery_pa_absolute"] < delivery:
        return dict(result, status="infeasible")
    savings = ((baseline["power_w"] - optimized["power_w"]) / 1000 * duration_h
               if result["baseline_meets_delivery"] else None)
    return dict(result, status="feasible", optimized=optimized, estimated_savings_kwh=savings)
