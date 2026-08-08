# Local DataHub infrastructure

This directory wraps the official DataHub Docker Quickstart for local Histograph development. The CLI and Quickstart release are pinned to `1.6.0`; the official CLI downloads and manages its generated Compose project under `~/.datahub/quickstart`.

The Quickstart is a local development environment, not a production deployment. It requires Docker Compose v2, `uv`, Python 3.13, and enough Docker resources for DataHub's dependencies.

## Start and bootstrap

Run the complete local DataHub setup from the repository root:

```bash
./infra/datahub/bootstrap.sh
```

The command starts DataHub, waits for GMS and the frontend, creates a local access token using the default Quickstart credentials, and writes the generated Histograph environment to `infra/datahub/.env`.

Load the environment before running Histograph:

```bash
set -a
source infra/datahub/.env
set +a
uv run uvicorn histograph.api.main:app --app-dir server/src --reload
```

The default local endpoints are:

- GMS: `http://localhost:8080`
- Frontend: `http://localhost:9002`
- Default credentials: `datahub` / `datahub`

## Health and lifecycle

```bash
./infra/datahub/health.sh
./infra/datahub/mcp-health.sh
./infra/datahub/stop.sh
```

Use `DATAHUB_PULL_IMAGES=false` when the pinned images are already present. Set `DATAHUB_MYSQL_PORT`, `DATAHUB_KAFKA_BROKER_PORT`, or `DATAHUB_ELASTIC_PORT` when those host ports are already occupied.

The reference ML graph and its seed data belong in `demo/`; this layer only provisions and authenticates the DataHub instance.
