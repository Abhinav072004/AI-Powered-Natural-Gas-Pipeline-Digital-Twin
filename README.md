# AI-Powered Natural Gas Pipeline Digital Twin

An independent academic pipeline monitoring and decision-support prototype for a 296.105 km virtual recreation of the Bokaro–Angul Pipeline Odisha section. All telemetry, pipeline dimensions, operating conditions, alerts, and energy savings are simulated. The project has no connection to GAIL operational systems and exposes no physical equipment control interface.

## Run the prototype

Requires Docker Engine and Docker Compose. From the repository root, start the stack:

```sh
docker compose up -d --build --wait --wait-timeout 180
```

Open the dashboard at `http://127.0.0.1:8080`. The first start builds the frontend and backend, applies the database schema, and trains the synthetic detection and maintenance models. The dashboard opens in normal scenario replay. Select from ten scenarios, or choose **Live MQTT stream** and publish a run:

```sh
docker compose run --rm --no-deps publisher --scenario large_leak --period 2 --steps 24 --run-id leak-demo-01
python scripts/smoke.py --run-id leak-demo-01
```

The period controls playback speed in wall-clock seconds. Measurements retain the configured 60-second simulation interval. Use a new run ID for each publish. With no incoming MQTT readings, the live view reports past data as stale after the configured timeout.

If container builds run behind a trusted HTTPS interception proxy, supply the machine's trusted CA bundle using the optional Compose override:

```sh
TWIN_BUILD_CA_FILE=/etc/ssl/certs/ca-certificates.crt \
  docker compose -f compose.yaml -f compose.proxy.yaml up -d --build --wait --wait-timeout 180
```

Use `docker compose ps -a` for service state and `docker compose logs` for troubleshooting. `docker compose down` stops the stack and retains named data volumes. The default configuration binds only to the loopback interface and uses an isolated development database and broker.

## Develop and reproduce

Requires Python 3.12, uv and Node.js 24 for the commands below. Run from the repository root:

```sh
uv sync --locked --no-install-project --extra xgboost
uv run --no-sync pytest -q
uv run --no-sync python -m pipeline_twin.simulation dataset --rounds 2 --steps 32 --csv
uv run --no-sync python -m pipeline_twin.detection --xgboost
uv run --no-sync python -m pipeline_twin.maintenance

npm --prefix frontend ci
npm --prefix frontend run build
```

Dataset generation writes JSONL episodes and optional CSV frame summaries under `artifacts/data`. Regenerate the data and models when changing the illustrative simulation assumptions.

For dashboard development, run `uv run --no-sync uvicorn pipeline_twin.api:app --reload` and `npm --prefix frontend run dev` in separate terminals. Vite forwards API requests to port 8000. Without `DATABASE_URL`, it runs scenario replays, analytics and retrieval in demo-only mode. Compose is required for the documented persistent review and live telemetry workflow.

The end-to-end smoke test uses the standard library. For the browser workflow, start the Compose stack, install frontend dependencies, then run `CHROMIUM_PATH=/usr/bin/chromium npm --prefix frontend run smoke:browser`. Set `TWIN_BASE` for a different local endpoint.

## Copilot

The default mode retrieves and cites passages from the prototype corpus using local embeddings and ChromaDB. Configure `LLM_BASE_URL` with a trusted OpenAI-compatible endpoint ending in `/v1`, `LLM_MODEL`, and the optional `LLM_API_KEY` to generate answers from retrieved material. Store credentials outside Git. Only the selected synthetic snapshot summary and retrieved excerpts are sent to the configured provider.

To index additional source PDFs in a local run, set `KNOWLEDGE_PDF_DIRECTORY` to a folder containing the PDFs and a `manifest.json` array. Each entry specifies `file`, `title` and `reference`. To use the same corpus in Compose, mount that folder read-only on the API container and set `KNOWLEDGE_PDF_DIRECTORY` to the mount path. The original GAIL proposal and current PNGRB regulation PDFs still need to be provided or verified before ingestion.

## Project references

- [Engineering design and phase gates](docs/engineering-design.md)
- [Case-study provenance and assumptions](docs/engineering-assumptions.md) · [Simulation configuration](config/case_study.toml)
- [System architecture](docs/architecture.md) · [Engineering validation](docs/engineering-validation.md)
- [Detection and maintenance evaluation](docs/model-evaluation.md) · [Demonstration scenarios](docs/demonstration.md)

## Resume project description

Built an academic natural-gas pipeline digital twin for a 296.105 km virtual transmission segment. Implemented Peng–Robinson gas properties, compressible hydraulics, implicit linepack simulation, hybrid leak detection, compressor energy comparison and predictive maintenance. Integrated simulated MQTT sensors, TimescaleDB, FastAPI, a React monitoring dashboard and a cited engineering copilot in Docker Compose.
