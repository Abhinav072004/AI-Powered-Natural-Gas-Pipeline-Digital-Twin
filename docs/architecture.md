# System architecture

The prototype uses independently testable Python modules and a React dashboard. Docker Compose will run the components that require separate processes. The analytics modules can run as libraries inside a worker or API process. Keeping their data contracts explicit will allow extraction into separate services if workload warrants it.

```mermaid
flowchart LR
    sim["Scenario runner and synthetic sensors"]
    twin["Hydraulic model and gas properties"]
    broker["Mosquitto MQTT broker"]
    ingest["Telemetry ingestion worker"]
    store[("PostgreSQL + TimescaleDB")]
    analysis["Analytics worker"]
    api["FastAPI dashboard API"]
    ui["React + TypeScript dashboard"]
    docs["Public documents and prototype references"]
    index[("ChromaDB vector index")]
    copilot["Engineering copilot"]
    llm["Configured language model"]

    twin --> sim
    sim -->|"Simulated telemetry"| broker
    broker --> ingest
    ingest -->|"Validate and persist"| store
    store -->|"Ordered observations"| analysis
    twin --> analysis
    analysis -->|"Predictions, alerts and health"| store
    store --> api
    api -->|"Evaluate a hypothetical scenario"| twin
    ui <-->|"HTTP queries and live event stream"| api
    docs -->|"PDF extraction, chunking and embeddings"| index
    api <-->|"Questions and cited responses"| copilot
    index -->|"Retrieved text and citations"| copilot
    store -->|"Read-only synthetic context"| copilot
    copilot <-->|"Retrieved context and answer"| llm
```

## Component responsibilities

| Component | Responsibilities and implementation target |
| --- | --- |
| Scenario runner | Python, NumPy and Pandas. Generate reproducible scenarios and bounded streams of sensor readings. Write scenario truth to experiment outputs. |
| Gas properties and hydraulic model | Use Peng–Robinson, Darcy–Weisbach and finite-volume inventory. Isolate gas properties behind a tested interface so CoolProp can be evaluated later where suitable. |
| Telemetry transport and ingestion | Publish through Mosquitto. Validate schemas with Pydantic. Persist data quality and handle missing, late and duplicate messages. |
| State and event store | PostgreSQL with TimescaleDB hypertables for observations and model outputs, and relational tables for the instrument catalog and assessment metadata. |
| Analytics | Physics residuals and Scikit-learn, with XGBoost and PyTorch as additional model paths. Estimate anomalies, segment likelihood, maintenance priorities, and risk. |
| Optimization | Use SciPy to compare hypothetical operating points against simulated delivery constraints. |
| FastAPI | Provide read endpoints for dashboard state and history, scenario evaluation, risk review, and copilot questions. Serve initial snapshots plus a reconnectable event stream. |
| Dashboard | React, TypeScript, Tailwind CSS and Plotly. Provide Executive Overview, Digital Twin, Leak Detection, Energy Optimization, Predictive Maintenance, Safety and Risk, and Engineering Copilot views. |
| Copilot | LangChain, Sentence Transformers and ChromaDB. Extract PDFs, index text with page provenance, retrieve before generation, and cite sources. |
| Deployment | Docker Compose for API, dashboard, database, broker, publisher, worker and the selected retrieval runtime. Use readiness checks and database migrations. |

## Data contracts

- Each telemetry envelope carries schema version, run ID, source message ID, sensor ID, segment and boundary association, UTC observation time, typed value, unit, and quality. The ingestion worker records arrival time independently.
- Use MQTT QoS 1 on `prototype/telemetry/v1/{run_id}/{sensor_id}`. A deduplication constraint including the observation timestamp and message identity makes replay safe. Record rejected envelopes separately. Broker access uses isolated service credentials and topic permissions when deployed.
- Model outputs carry the telemetry time range, run ID, model or equation version, evidence, output timestamp, and quality. Findings persist independently of dashboard subscriptions so that clients can recover after reconnecting.
- The dashboard presents quality flags and explicitly labels simulated readings. If a client misses events, it requests a fresh snapshot before resuming updates. Scenario evaluation returns inputs, constraints, outputs and the model version.
- The copilot keeps source document citations distinct from current synthetic observations. The retrieval index records document title, revision, source URL, page, and content fingerprint. Treat extracted text as evidence. If retrieval finds insufficient evidence, give the user the available references and explain the gap.
- API calls and broker topics expose monitoring, assessment, and simulation. The prototype contains no route, topic, adapter, or copilot tool that can send commands to physical equipment. Record human acknowledgements as application events.

## Deployment and validation boundaries

The first deployment target is a reproducible local Compose environment. Only the dashboard or gateway should be exposed by default. Keep database and broker on internal networks and persist data in named volumes. Use an approved local or hosted text model through configuration when generation is integrated. Keep its credentials out of the repository. The GAIL proposal PDF, verified versions of regulations, and choice of model and hosting target remain open at this phase.
