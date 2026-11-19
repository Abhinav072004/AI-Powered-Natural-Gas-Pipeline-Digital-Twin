"""Single-phase isothermal pipeline calculations. All dimensional inputs use SI."""

from dataclasses import dataclass
from math import exp, isfinite, log10, pi, sqrt
from pathlib import Path
import tomllib

import numpy as np
from scipy.integrate import solve_ivp
from scipy.optimize import brentq, root

R = 8.314462618
CONFIG = Path(__file__).resolve().parents[1] / "config/case_study.toml"
# M (kg/mol), critical temperature (K), critical pressure (Pa), acentric factor.
COMPONENTS = {
    "methane": (0.016043, 190.564, 4.5992e6, 0.01142),
    "ethane": (0.030070, 305.322, 4.8722e6, 0.0995),
    "propane": (0.044097, 369.89, 4.2512e6, 0.1521),
    "nitrogen": (0.0280134, 126.192, 3.3958e6, 0.0372),
    "carbon_dioxide": (0.04401, 304.1282, 7.3773e6, 0.22394),
}


@dataclass(frozen=True)
class GasProperties:
    molecular_weight_kg_mol: float
    compressibility: float
    density_kg_m3: float
    viscosity_pa_s: float


class Gas:
    def __init__(self, composition: dict[str, float], temperature_k: float):
        if not composition or any(
            name not in COMPONENTS or not isfinite(value) or value < 0
            for name, value in composition.items()
        ) or not np.isclose(sum(composition.values()), 1, rtol=0, atol=1e-9):
            raise ValueError("Supported gas mole fractions must sum to one")
        if not 275 <= temperature_k <= 340:
            raise ValueError("The prototype gas temperature envelope is 275–340 K")
        self.temperature = temperature_k
        fractions = np.array(list(composition.values()))
        molar_mass, tc, pc, omega = np.array([COMPONENTS[name] for name in composition]).T
        self.molecular_weight = float(fractions @ molar_mass)
        kappa = 0.37464 + omega * (1.54226 - 0.26992 * omega)
        a = 0.45724 * (R * tc) ** 2 / pc * (1 + kappa * (1 - np.sqrt(temperature_k / tc))) ** 2
        b = 0.07780 * R * tc / pc
        self.a_per_pa = float((fractions @ np.sqrt(a)) ** 2 / (R * temperature_k) ** 2)
        self.b_per_pa = float((fractions @ b) / (R * temperature_k))
        molar_g = self.molecular_weight * 1000
        rankine = temperature_k * 1.8
        self.lee_k = (9.379 + 0.01607 * molar_g) * rankine**1.5 / (209.2 + 19.26 * molar_g + rankine)
        self.lee_x = 3.448 + 986.4 / rankine + 0.01009 * molar_g
        self.lee_y = 2.447 - 0.2224 * self.lee_x

    def at(self, pressure_pa: float) -> GasProperties:
        if not 1e5 <= pressure_pa <= 1e7:
            raise ValueError("The prototype gas pressure envelope is 1–100 bar(a)")
        a, b = self.a_per_pa * pressure_pa, self.b_per_pa * pressure_pa
        roots = np.roots([1, b - 1, a - 3*b*b - 2*b, -a*b + b*b + b**3])
        vapor_roots = [float(z.real) for z in roots if abs(z.imag) < 1e-9 and z.real > b]
        if not vapor_roots:
            raise ValueError("No physical Peng–Robinson vapor root")
        z = max(vapor_roots)
        density = pressure_pa * self.molecular_weight / (z * R * self.temperature)
        viscosity = 1e-7 * self.lee_k * exp(self.lee_x * (density / 1000)**self.lee_y)
        return GasProperties(self.molecular_weight, z, density, viscosity)


def friction_factor(reynolds: float, roughness_ratio: float) -> float:
    if reynolds == 0:
        return 0.0
    if reynolds <= 2300:
        return 64 / reynolds
    turbulent = brentq(
        lambda inverse_sqrt: inverse_sqrt + 2 * log10(roughness_ratio / 3.7 + 2.51 * inverse_sqrt / reynolds),
        1, 30,
    ) ** -2
    weight = min((reynolds - 2300) / 1700, 1)
    return (1 - weight) * 64 / reynolds + weight * turbulent


@dataclass(frozen=True)
class Segment:
    segment_id: int
    start_km: float
    end_km: float
    inlet_pressure_pa_absolute: float
    outlet_pressure_pa_absolute: float
    pressure_drop_pa: float
    mean_density_kg_m3: float
    velocity_m_s: float
    reynolds: float
    darcy_friction: float
    mass_flow_kg_s: float
    inventory_kg: float
    temperature_k: float


def read_case(path: Path = CONFIG) -> dict:
    with path.open("rb") as handle:
        return tomllib.load(handle)


class Pipeline:
    def __init__(self, simulation: dict):
        self.settings = simulation
        self.bounds_km = np.asarray(simulation["segment_boundaries_km"], dtype=float)
        self.lengths = np.diff(self.bounds_km) * 1000
        self.diameter = float(simulation["pipe_inner_diameter_m"])
        self.roughness = float(simulation["pipe_absolute_roughness_m"])
        if (
            len(self.bounds_km) < 2 or self.bounds_km[0] != 0
            or not np.all(np.isfinite(self.bounds_km)) or np.any(self.lengths <= 0)
            or not 0 <= self.roughness < self.diameter
            or simulation.get("elevation_change_m", 0) != 0
        ):
            raise ValueError("Expected increasing flat pipeline boundaries and valid geometry")
        self.area = pi * self.diameter**2 / 4
        self.volumes = self.area * self.lengths
        self.gas = Gas(simulation["gas_mole_fractions"], simulation["temperature_k"])

    def steady(self, inlet_pressure_pa: float | None = None, flow_kg_s: float | None = None,
               *, tolerance: float = 1e-7) -> list[Segment]:
        pressure = self.settings["inlet_pressure_pa_absolute"] if inlet_pressure_pa is None else inlet_pressure_pa
        self.gas.at(pressure)
        flow = self.settings["delivery_mass_flow_kg_s"] if flow_kg_s is None else flow_kg_s
        if not isfinite(flow) or flow < 0:
            raise ValueError("Steady delivery flow must be finite and nonnegative")
        flux = flow / self.area

        def derivatives(_distance, state):
            props = self.gas.at(sqrt(state[0])) if state[0] > 0 else self.gas.at(0)
            re = flux * self.diameter / props.viscosity_pa_s
            friction = friction_factor(re, self.roughness / self.diameter)
            return (-friction * flux**2 * props.compressibility * R * self.gas.temperature /
                    (self.diameter * props.molecular_weight_kg_mol), self.area * props.density_kg_m3)

        results = []
        for index, length in enumerate(self.lengths):
            solution = solve_ivp(derivatives, (0, length), [pressure**2, 0.0], rtol=tolerance)
            if not solution.success:
                raise ValueError("Pressure integration failed")
            pressure_squared, inventory = solution.y[:, -1]
            end = sqrt(pressure_squared)
            density = inventory / self.volumes[index]
            props = self.gas.at((pressure + end) / 2)
            velocity = flux / density
            if velocity > 0.15 * sqrt(1.3 * R * self.gas.temperature / self.gas.molecular_weight):
                raise ValueError("Velocity exceeds the prototype low-Mach envelope")
            re = flux * self.diameter / props.viscosity_pa_s
            results.append(Segment(
                index + 1, float(self.bounds_km[index]), float(self.bounds_km[index + 1]),
                pressure, end, pressure - end, density, velocity, re,
                friction_factor(re, self.roughness / self.diameter), flow, inventory, self.gas.temperature,
            ))
            pressure = end
        return results


@dataclass(frozen=True)
class Snapshot:
    pressures_pa: np.ndarray
    boundary_pressures_pa: np.ndarray
    inventory_kg: np.ndarray
    face_flows_kg_s: np.ndarray
    leaks_kg_s: np.ndarray


class Linepack:
    """Implicit finite-volume update with frozen, steady-state face resistances."""

    def __init__(self, pipeline: Pipeline):
        self.pipeline = pipeline
        steady = pipeline.steady()
        baseline_flow = steady[0].mass_flow_kg_s
        if baseline_flow <= 0:
            raise ValueError("The linepack resistance calibration requires positive baseline flow")
        self.pressures = np.array([
            brentq(lambda p: pipeline.gas.at(p).density_kg_m3 - segment.mean_density_kg_m3,
                   1e5, 1e7)
            for segment in steady
        ])
        upstream = np.r_[steady[0].inlet_pressure_pa_absolute, self.pressures[:-1]]
        upstream_half = self.pressures**2 - np.array([s.outlet_pressure_pa_absolute for s in steady])**2
        face_drop = upstream**2 - self.pressures**2
        self.resistance = face_drop / baseline_flow**2
        self.upstream_share = np.r_[0, upstream_half[:-1]] / face_drop
        self.outlet_resistance = upstream_half[-1] / baseline_flow**2
        self.inventory = np.array([s.inventory_kg for s in steady])
        self.baseline = Snapshot(
            self.pressures.copy(),
            np.array([steady[0].inlet_pressure_pa_absolute, *(s.outlet_pressure_pa_absolute for s in steady)]),
            self.inventory.copy(), np.full(len(steady) + 1, baseline_flow), np.zeros(len(steady)),
        )

    def step(self, inlet_pa: float, demand_kg_s: float, dt_s: float,
             leaks_kg_s=None) -> Snapshot:
        self.pipeline.gas.at(inlet_pa)
        leaks = np.zeros_like(self.pressures) if leaks_kg_s is None else np.asarray(leaks_kg_s, dtype=float)
        if (not isfinite(dt_s) or dt_s <= 0 or not isfinite(demand_kg_s) or demand_kg_s < 0
                or leaks.shape != self.pressures.shape or np.any(~np.isfinite(leaks) | (leaks < 0))):
            raise ValueError("Invalid time step, delivery demand, or simulated withdrawals")

        def state(pressure):
            masses = self.pipeline.volumes * [self.pipeline.gas.at(p).density_kg_m3 for p in pressure]
            square_drop = np.r_[inlet_pa, pressure[:-1]]**2 - pressure**2
            flows = np.r_[np.sign(square_drop) * np.sqrt(np.abs(square_drop) / self.resistance), demand_kg_s]
            return masses, flows

        def imbalance(scaled_pressure):
            masses, flows = state(scaled_pressure * 1e6)
            return ((masses - self.inventory) / dt_s - flows[:-1] + flows[1:] + leaks)

        solution = root(imbalance, self.pressures / 1e6, tol=1e-9)
        pressures = solution.x * 1e6
        if np.max(np.abs(imbalance(solution.x))) > 1e-5:
            raise ValueError(f"Linepack update did not conserve mass: {solution.message}")
        masses, flows = state(pressures)
        faces_squared = (np.r_[inlet_pa, pressures[:-1]]**2
                         - self.upstream_share * self.resistance * flows[:-1] * np.abs(flows[:-1]))
        outlet_squared = pressures[-1]**2 - self.outlet_resistance * demand_kg_s**2
        if outlet_squared < 1e10:
            raise ValueError("Delivery pressure fell outside the model envelope")
        self.pressures, self.inventory = pressures, masses
        return Snapshot(pressures.copy(), np.sqrt(np.r_[faces_squared, outlet_squared]),
                        masses.copy(), flows, leaks.copy())
