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
