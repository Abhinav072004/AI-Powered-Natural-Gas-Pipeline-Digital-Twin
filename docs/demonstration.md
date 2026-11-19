# Demonstration scenarios

The scenario selector replays a seeded 40-sample episode, showing its final state and timeline. The separate MQTT publisher streams those kinds of episodes into TimescaleDB using a configurable playback period. Model findings describe the generated telemetry and depend on coverage, measurement error and the fitted classifier.

| Scenario | What to observe |
| --- | --- |
| Normal operation | Inlet and delivery pressure, linepack, and stable equipment indicators |
| Demand increase | Delivery flow rises and pressure falls as inventory adjusts |
| Pressure drop | Falling inlet pressure and a coherent trend along the virtual pipe |
| Large simulated leak | Persistent mass imbalance, leak classification and a possible affected segment |
| Small simulated leak | Weaker residuals, delayed indication and possible misses |
| Pressure sensor drift | An artificial local gradient discrepancy |
| Flow meter fault | Incorrect or missing delivery flow and reduced availability |
| Compressor degradation | Rising vibration and discharge temperature with lower health |
| Communication failure | Missing pressure and flow values and a communications classification |
| Abnormal valve indication | Changed virtual valve indication and a maintenance review prompt |

In **Energy optimization**, compare the default 60 kg/s delivery at 45 bar(a), then request 80 bar(a) to exercise the infeasible result. In **Safety & risk**, select a probability and severity, review the educational response, and save an application review. In **Engineering copilot**, ask about linepack and compare the retrieved sources with the separate simulation context.

## End-to-end verification

The system test checks dashboard assets, health and TimescaleDB connectivity, simulation replay, a detected leak, a communications fault, optimizer output, a saved risk review, and copilot citations. Starting a publisher lets it also check MQTT-to-API delivery. The browser smoke test opens all seven views and exercises segment selection, replay switching, engineering forms, citations and a mobile viewport.

For an accelerated test of stale telemetry, start Compose with `TELEMETRY_STALE_AFTER_S=12`, start a publisher and run `python scripts/smoke.py --run-id <run-id> --expect-stale` while the publisher is active.

### Verified cloud development run

The local Compose deployment passed the smoke test with real Mosquitto and TimescaleDB containers. A 24-interval abnormal replay stored 624 readings in the telemetry hypertable. A separate duplicate-message test preserved the stored row count. The dashboard API reported the stopped stream as stale and cleared its current readings. Latest-frame inference took 10.77 ms on the normal replay during this run.

All 20 Python tests passed. Chromium passed all seven dashboard views, a segment selection, scenario switching, the energy and risk forms, copilot citations, and the 390 px mobile viewport. The configured LLM interface was tested against a mocked response. The deployed smoke test used local cited retrieval.
