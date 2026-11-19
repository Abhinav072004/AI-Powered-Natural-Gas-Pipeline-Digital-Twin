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
