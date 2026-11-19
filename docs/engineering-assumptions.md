# Engineering assumptions

## Case-study provenance

This independent academic prototype uses the Bokaro–Angul Pipeline Odisha section of the Jagdishpur–Haldia–Bokaro–Dhamra Pipeline as a case study. The case-study figures below come from the project brief, which attributes them to GAIL’s project proposal. The proposal PDF and page references are pending verification.

| Figure | Value supplied in the brief |
| --- | ---: |
| Odisha section length | 296.105 km |
| Villages crossed | 212 |
| Forest divisions | 7 |
| Districts | 5 |
| Forest land | 65.4036 ha |
| Non-forest land | 658.5433 ha |

Source leads for verification and ingestion are the official PARIVESH portal for the proposal and the Petroleum and Natural Gas Regulatory Board (PNGRB) for regulations. Record title, date or revision, URL, retrieval date, and page or clause before promoting any document into the copilot’s reference corpus. [PARIVESH](https://parivesh.nic.in/) · [PNGRB](https://pngrb.gov.in/)

## Illustrative simulation inputs

[Case-study configuration](../config/case_study.toml) separates brief-derived case-study figures from adjustable simulation inputs. All operating data, equipment specifications, and results in the prototype are synthetic. Distances are along a virtual centerline and the segment boundaries and stations are artificial.

| Input | Starting value | Role in the model |
| --- | --- | --- |
| Boundaries | 0, 40, 80, 120, 160, 200, 240, 270, 296.105 km | Eight consecutive virtual segments |
| Pipe inner diameter | 0.76 m | Cross-sectional area, inventory, and friction |
| Absolute roughness | 45 µm | Relative roughness for friction |
| Elevation change | 0 m | Flat baseline model |
| Inlet pressure | 65 bar(a) | Fixed inlet boundary and baseline compressor discharge |
| Gas temperature | 300 K | Isothermal pipeline baseline |
| Delivery mass flow | 60 kg/s | Fixed outlet withdrawal in steady state |
| Compressor suction pressure | 45 bar(a) | Compressor power calculation |
| Compressor efficiency | 0.78 | Illustrative isentropic efficiency |
| Heat capacity ratio | 1.30 | Baseline constant heat capacity ratio for compressor calculations |
| Minimum delivery pressure | 45 bar(a) | Illustrative optimization constraint |
| Maximum discharge pressure | 75 bar(a) | Illustrative optimization constraint |
| Gas mole fractions | CH₄ 0.940, C₂H₆ 0.035, C₃H₈ 0.010, N₂ 0.010, CO₂ 0.005 | Mixture molecular weight and properties |
| Sampling interval and seed | 60 s, 42 | Reproducible scenario generation |

The configuration models a single gas-phase pipe with uniform diameter and roughness. Wall thickness, material, maximum allowable operating pressure, terrain, detailed heat transfer, actual station coordinates and compressor maps would need independent inputs. Treat the proposed discharge ceiling as an academic scenario constraint.

Use SI units internally. JSON field names carry physical units and use absolute pressure, for example `pressure_pa_absolute`. Convert to bar(a), km and MW at the dashboard. Store linepack as mass in kilograms. Any standard volume reported later must state reference temperature, absolute pressure and the density or compressibility at those conditions.

## Virtual station and sensor layout

Receiving and compression share the inlet boundary. Delivery sits at the final boundary. Sectionalizing valves are placed at boundaries 2, 4, and 6 and report status only. Inlet and outlet flows are metered. The digital twin uses pressure and temperature stations at every virtual boundary to support inventory estimation and segment-level comparisons.

| Tag | Signal | Virtual location |
| --- | --- | --- |
| PT-101 | Inlet pressure | Boundary 0 |
| PT-102 | Segment pressure | Boundary 4 as the reference tag, with distinct tags for the other interior boundaries |
| PT-103 | Outlet pressure | Boundary 8 |
| FT-101 | Inlet mass flow | Boundary 0 |
| FT-102 | Outlet mass flow | Boundary 8 |
| TT-101 | Gas temperature | Boundary 0, with distinct tags downstream |
| TT-102 | Compressor discharge temperature | Compressor |
| VIB-101 | Compressor vibration | Compressor |
| PWR-101 | Compressor input power | Compressor |
| XV-101 | Valve status | Boundary 2, with distinct tags at the other valve stations |

Pressure and flow measurements have separate error models, health flags, and timestamps. Exact on-pipe leak position is outside the inference target. Segment estimates reflect the illustrative measurement geometry and must be evaluated on held-out synthetic events.
