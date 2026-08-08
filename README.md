# Histograph

Histograph is a production ML incident-response platform. It receives model predictions, delayed outcomes, and deployment events; detects deterministic abnormalities; investigates them through DataHub lineage; coordinates approved remediation; and verifies recovery.

The first implementation slice is the headless telemetry and detection core. It uses Postgres for control-plane state and ClickHouse for high-volume observations. The web client and reference ML environment are added on top of this API rather than being required to validate the core.

## Local services

The repository compose file starts the Histograph dependencies without touching any other Docker project:

```bash
docker compose up -d postgres clickhouse redis
```

Install the Python environment and run the checks:

```bash
uv sync --dev
uv run ruff check server/src server/tests
uv run pytest
```

Run the API after the services are healthy:

```bash
uv run uvicorn histograph.api.main:app --app-dir server/src --reload
```

The API is available at `http://localhost:8000`. Its first startup creates the Postgres control-plane tables and ClickHouse telemetry tables.

The headless flow is:

1. Send predictions, outcomes, or deployment events to `/v1/events`.
2. Create a monitor at `/v1/monitors` and run its detection endpoint.
3. Investigate a triggered incident at `/v1/investigations/{incident_id}` with its DataHub model URN.

An investigation reads the model entity and both directions of its DataHub lineage through MCP, records the exact tool trace and lineage evidence on the incident, and keeps the incident open until a dependency change is corroborated. Set `HISTOGRAPH_DATAHUB_MCP_MUTATIONS_ENABLED=true` and pass `write_back: true` only when the team has approved saving the investigation as a DataHub analysis document.

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
export HISTOGRAPH_DATAHUB_MCP_PACKAGE=mcp-server-datahub@latest
```

The local DataHub quickstart is separate from the Histograph compose project so its own dependencies and lifecycle remain isolated.
