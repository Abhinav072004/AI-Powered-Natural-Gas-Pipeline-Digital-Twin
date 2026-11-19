# Engineering design

This prototype compares simulated observations with engineering predictions and presents evidence for human review. The [engineering assumptions](engineering-assumptions.md) define the case-study provenance, model inputs, units, and virtual instrumentation. The [system architecture](architecture.md) defines data flow and service boundaries.

## Gas properties and hydraulics

Calculate mixture molecular weight from mole fractions, \(M = \sum_i y_i M_i\), then apply the Peng–Robinson equation of state for single-phase vapor. Use classical quadratic mixing for attraction, linear mixing for co-volume, and disclose the initial zero binary interaction parameters. Evaluate the physical vapor root with \(Z > B\) where \(B\) is the dimensionless co-volume parameter. Report invalid or out-of-domain states explicitly. Validate across the scenario envelope before using unusual mixtures or conditions near a phase boundary. Gas density is \(\rho = PM/(ZRT)\). Evaluate gas viscosity with the Lee–Gonzalez–Eakin correlation using its published unit conversions and document its applicability to the selected mixture.

The baseline solves for steady horizontal isothermal flow with a fixed inlet pressure and requested delivery mass flow. The low-Mach model neglects acceleration, elevation, shaft work inside pipe segments, and valve minor losses. The mass flux \(G = \dot m/A\), velocity \(u = G/\rho\) and Reynolds number \(Re = GD/\mu\) give the Darcy friction source

```text
dP/dx = -f_D G² / (2 D ρ)
d(P²)/dx = -(f_D G² / D) (Z R T / M)
```

Use \(64/Re\) for laminar flow and solve Colebrook–White for fully turbulent flow. Document how the transition band is handled and bypass friction at zero flow. Integrate pressure squared with local gas properties and Darcy friction. Reject a flow case if it lacks a positive-pressure solution or exits the model envelope. Separately report delivery constraint violations for valid solutions. With constant \(Z\) and \(f_D\), pressure squared decreases linearly and provides a closed-form benchmark. Expose segment inlet and outlet pressure, average density, pressure drop, velocity, Reynolds number, friction factor, mass flow, and gas inventory.

Compute steady inventory by spatial integration of \(A\rho(x)\). For dynamic scenarios, maintain a finite-volume inventory per segment and compute adjacent inter-segment flow from pressure differences using a quasi-steady momentum closure. Use the EOS to relate inventory and mean pressure, set source pressure and delivered demand as boundaries, and integrate conservation with time steps chosen for numerical stability. Apply leak withdrawal only to the selected simulation cell, and anchor or spin up dynamic runs before applying disturbances. This approximation supports slow linepack changes. Predicting fast pressure waves requires a separately validated transient momentum and thermal model.

```text
dM_i/dt = m_in,i - m_out,i - m_leak,i
residual = measured inlet flow - measured outlet flow - Δestimated inventory / Δt
```

Update the independent observed inventory estimate from timestamp-aligned boundary pressure and temperature readings. Report its quality and uncertainty. An interval with stale or absent required readings has an unavailable residual. Gate leak alerts on positive imbalance over consecutive usable intervals and combine that evidence with measured-versus-predicted pressure gradients. Characterize false alarms during normal linepack changes, demand shifts, sensor faults, and communications gaps.

## Synthetic scenario and model design

Each time step produces a pipeline state and a separate stream of sensor observations. Use correlated hydraulic responses to changed demand or loss, then apply seeded instrument noise, bias, dropout, stale measurements, and sample timing. Preserve event truth for training and scoring. Derive online features only from readings available by the inference timestamp. Include pipeline end flows, segment pressures, temperature, equipment readings, measurement quality, timestamps, and segment association. Keep ground truth labels and scenario controls outside online inference inputs.

| Scenario | Mechanism to exercise |
| --- | --- |
| Normal | Vary inlet and demand around steady operation with seeded measurement noise |
| Sudden demand increase | Step outlet withdrawal and track inventory and pressure response |
| Gradual pressure drop | Ramp inlet pressure within the model envelope |
| Sudden simulated leakage | Start a virtual segment withdrawal and observe imbalance |
| Small simulated leakage | Repeat at reduced withdrawal and across multiple locations |
| Pressure sensor drift | Ramp bias on a virtual transmitter while preserving hydraulic truth |
| Flow meter malfunction | Inject stuck or biased flow observations |
| Compressor degradation | Evolve correlated efficiency, temperature and vibration signals |
| Communication failure | Omit a block of observations and mark channels stale |
| Valve status abnormality | Inject an unexpected indication for review |

Split chronological runs into train, validation, and test blocks with all scenario types represented across independently seeded runs. Keep whole episodes in one split. Fit preprocessing and models on training only, and tune alarm persistence and decision thresholds on validation only. Compare Random Forest, SVM, and XGBoost when available against the physics-only baseline. Train Isolation Forest on normal training observations and use its anomaly score for novelty detection. Treat a PyTorch autoencoder as an optional comparison.

Evaluate precision, recall, F1, confusion matrices, ROC-AUC where probability scores support it, false alarms per normal hour, and event-level detection latency. Report missed events separately from latency. Score localization with segment accuracy and distance between true and estimated segment midpoints, stratified by leak size and observability. Return possible leakage, sensor malfunction, demand fluctuation, abnormal pressure, communication fault, or normal operation with supporting measurements. Display an unknown outcome when required data is insufficient.

## Energy optimization

Estimate compressor shaft power with a constant-isentropic-ratio baseline. At absolute suction and discharge pressures \(P_s\) and \(P_d\), use \(\dot W = \dot m c_p T_s [(P_d/P_s)^{(k-1)/k}-1]/\eta_s\) and \(c_p = k(R/M)/(k-1)\). Enforce positive absolute pressures, \(P_d \ge P_s\), and \(0 < \eta_s \le 1\). This simplified calculation omits driver losses and compressor-map constraints. A later extension can use EOS enthalpy at isentropic and actual discharge states.

Use SciPy to minimize power over bounded discharge pressure, at fixed delivery mass flow, subject to minimum delivery pressure and the hydraulic solution envelope. Evaluate the candidate through the full hydraulic solver. Report baseline and candidate powers, endpoint pressures, mass flow, model constraints, and savings over an explicitly stated duration. Return a clear infeasible result if no case can sustain delivery. The results describe hypothetical scenarios for review.

## Maintenance and risk

Generate correlated degradation features for compressors and repeatable drift or abnormal status for valves and instruments. Use chronological equipment episodes to estimate and validate a defined future-window failure probability under synthetic degradation. Combine that probability with configurable consequence, criticality, and recent anomaly frequency to rank maintenance priorities. Report the prediction horizon, feature reasons, health score, and suggested inspection. Remaining useful life is outside the planned model.

Use ordinal probability and severity scales from 1 to 5. For the initial configurable matrix, classify products 1–4 as low, 5–9 as medium, 10–15 as high, and 16–25 as critical. Record likelihood and consequence rationale. Include events for potential leakage, pressure deviation, equipment failure, third-party excavation, intrusion, environmental exposure, and isolation assessment. Example review actions are monitoring and logging for low, investigation for medium, escalation to the authorized duty engineer for high, and referral to the site's approved emergency procedures for critical. The prototype displays educational recommendations and records acknowledgement in the application. Field response belongs to authorized personnel under approved procedures.

Reference the PNGRB natural gas pipeline Technical Standards and Specifications including Safety Standards and Integrity Management System regulations. Confirm current versions and applicable amendments before citing individual requirements. [PNGRB](https://pngrb.gov.in/)

## Verification and phase gates

The Phase 1 design screen used the constant-property equation with illustrative values of Z = 0.90 and Darcy friction factor = 0.012. The configured mixture has a calculated molecular weight of 17.0740 g/mol. At 60 kg/s, the screen gives an outlet pressure of 56.12 bar(a), against the illustrative 45 bar(a) delivery minimum. It yields a flat profile at zero flow and a lower outlet pressure at higher flow. Phase 2 will test the numerical solver with local gas properties and friction.

| Phase | Deliverable and required evidence |
| --- | --- |
| 1. Design | Verify case configuration boundaries, mixture totals, units and ranges. Screen the baseline with a closed-form pressure calculation. Review the architecture and assumptions. |
| 2. Hydraulics | Test EOS and viscosity reference states, the zero-flow limit, analytical pressure drop, spatial convergence, inventory, and dynamic mass conservation. Record limits in an engineering validation report. |
| 3. Sensor dataset | Generate all ten scenario types. Check reproducibility, unit and quality validation, event coverage, and split isolation. Provide a MQTT demonstration publisher. |
| 4. Detection | Train and compare models. Reproduce metrics, latency, error analysis, and localization from held-out runs. Save or reproducibly generate versioned model artifacts. |
| 5. Optimization | Check zero compression ratio, compressor reference calculations, feasibility, delivery constraints, and scenario energy savings. |
| 6. Maintenance | Validate failure scores and maintenance ranking on held-out degradation episodes. |
| 7. Backend and database | Exercise validated MQTT ingestion, TimescaleDB writes and replay, FastAPI endpoints, risk assessment, fault handling, and inference latency. |
| 8. Dashboard | Build and test the seven views, engineering visualizations, refresh, missing-data states, and demonstration flows. |
| 9. Copilot | Validate ingestion, retrieval, source and page references, telemetry attribution, and insufficient-evidence handling. |
| 10. Deployment | Run the Docker Compose stack with normal and abnormal demonstrations. Finish the reproducibility guides, validation reports, and resume-ready description. Evaluate cloud hosting when a target is available. |

Each phase ends with a verified change, a review of open issues, and confirmation before starting the next major phase.
