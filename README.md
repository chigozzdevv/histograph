# Histograph

Histograph is a production ML incident-response platform. It receives model predictions, delayed outcomes, and deployment events; detects deterministic abnormalities; investigates them through DataHub lineage; coordinates approved remediation; and verifies recovery.

The first implementation slice is the headless telemetry and detection core. It uses Postgres for control-plane state and ClickHouse for high-volume observations. The web client and reference ML environment are added on top of this API rather than being required to validate the core.

## Local services

The repository compose file starts the Histograph dependencies without touching any other Docker project:

```bash
./scripts/compose.sh up -d postgres clickhouse redis
```

Install the Python environment and run the checks:

```bash
uv sync --dev
uv run ruff check server/src server/tests
uv run pytest
```

With Postgres and ClickHouse running, execute the database-backed API flow as well:

```bash
HISTOGRAPH_RUN_INTEGRATION=1 uv run pytest server/tests/integration
```

Run the API after the services are healthy:

```bash
uv run uvicorn histograph.api.main:app --app-dir server/src --reload
```

The API is available at `http://localhost:8000`. Startup applies checksummed Postgres and ClickHouse migrations before accepting traffic.

The headless flow is:

1. Register the model and its binary-class semantics at `/v1/models/{model_name}`.
2. Send predictions, outcomes, or deployment events to `/v1/events`.
3. Create a versioned monitor at `/v1/monitors`, or report deployment state so Histograph can
   resolve a monitor without an explicit version.
4. Run the monitor's detection endpoint.
5. Investigate a triggered incident at `/v1/investigations/{incident_id}`. Histograph resolves the
   DataHub URN from the model registration rather than accepting it from the investigation request.

The implemented performance evaluator supports binary classification with an explicit positive
prediction class and actual-outcome value. The implemented drift evaluator supports numeric-feature
PSI. Monitor creation rejects signal and metric combinations that are not implemented yet, and each
monitor requires a minimum sample size before it can trigger an incident.

An investigation reads the model entity and both directions of its DataHub lineage through MCP, records the exact tool trace and lineage evidence on the incident, and keeps the incident open until a dependency change is corroborated. Set `HISTOGRAPH_DATAHUB_MCP_MUTATIONS_ENABLED=true` and pass `write_back: true` only when the team has approved saving the investigation as a DataHub analysis document.

An incident can enter `resolved` only after persisted recovery evidence contains at least one passed
verification check. A responsible engineer can instead set it to `closed`, but a manual closure
requires a reason and is recorded separately in the incident timeline.

## DataHub

Histograph connects to a self-hosted DataHub GMS endpoint through the official DataHub MCP server. The integration uses the read-only entity and lineage tools during investigations and writes incident evidence only through an explicit write-back path.

Bootstrap the local DataHub environment with the pinned Quickstart wrapper:

```bash
./infra/datahub/bootstrap.sh
set -a
source infra/datahub/.env
set +a
```

Run `./infra/datahub/health.sh` to check GMS and the frontend. Stop the local DataHub instance with `./infra/datahub/stop.sh`.

```bash
export HISTOGRAPH_DATAHUB_GMS_URL=http://localhost:8080
export HISTOGRAPH_DATAHUB_GMS_TOKEN=<token>
export HISTOGRAPH_DATAHUB_MCP_COMMAND=uvx
export HISTOGRAPH_DATAHUB_MCP_PACKAGE=mcp-server-datahub==0.6.0
export HISTOGRAPH_DATAHUB_MCP_PYTHON=3.13
```

The local DataHub quickstart is separate from the Histograph compose project so its own dependencies and lifecycle remain isolated.
