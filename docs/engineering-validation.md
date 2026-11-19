# Engineering validation

## Hydraulic simulator

Run the checks with `uv sync --locked --no-install-project` and `uv run --no-sync pytest -q`.

| Check | Result |
| --- | --- |
| Pure methane at 300 K and 50 bar(a) | Peng–Robinson vapor root 0.90183, density 35.6595 kg/m³, estimated viscosity 12.475 µPa·s |
| Zero flow | Uniform inlet pressure, zero velocity and inventory equal to density times pipe volume |
| Constant properties | Outlet 56.12 bar(a), consistent with analytically integrating the pressure-squared equation |
| Default mixture with local properties | Outlet 57.04 bar(a) and linepack 6.460 million kg at 60 kg/s |
| Solver convergence and flow sensitivity | Tightening the integration tolerance from 10⁻⁷ to 10⁻¹⁰ changes default outlet pressure and linepack by less than one part per million. Raising delivery flow to 70 kg/s lowers outlet pressure. |
| Implicit linepack conservation | The model holds the steady baseline and closes all segment mass balances to within 1 g over a 60-second demand and withdrawal disturbance. |

The dynamic model freezes steady-state pressure-squared face resistances around the positive-flow baseline. It uses backward Euler for storage and pressure-dependent Peng–Robinson density. It models slow deviations around that baseline and assumes the bulk gas stays in a single vapor phase. The state calculations are academic and have no field calibration. Fast wave propagation, heat transfer, elevation, and phase stability are outside the implemented model. The methane check validates a numerical EOS reference point, and field-property or instrument validation requires separate data.

## Compressor and energy comparison

The compressor equation yields zero power at a unit pressure ratio. At 60 kg/s, 45 bar(a) suction, 65 bar(a) discharge and 78% isentropic efficiency, predicted temperature is 334.1 K and baseline shaft power is 4.313 MW. SciPy brackets the minimum simulated discharge pressure that sustains 45 bar(a) at delivery. The default case yields about 54.94 bar(a) discharge and 2.295 MW, a simulated difference of 2,017 kWh over one hour. A demand for 80 bar(a) delivery is reported infeasible with the configured ceiling. This calculation uses constant heat capacity and excludes compressor maps, driver losses, and field constraints.
