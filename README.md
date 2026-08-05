# Histograph

Histograph is continuous assurance for DataHub-powered agents. It reads organizational context from DataHub, executes an analytics agent, captures the agent's tool calls, SQL, results, and final answer, and applies deterministic checks before reporting a pass or regression.

## Current system

The repository contains a working vertical execution path:

```text
DataHub MCP connection
        ↓
DataHub context discovery
        ↓
DataHub Analytics Agent execution
        ↓
SSE evidence capture
        ↓
SQL, result, asset, and response evaluation
        ↓
Persisted run result
        ↓
Histograph dashboard
```

The Analytics Agent adapter follows the upstream API directly:

- `GET /health`
- `POST /api/conversations`
- `POST /api/conversations/{conversation_id}/messages`
- `TEXT`, `TOOL_CALL`, `TOOL_RESULT`, `SQL`, `CHART`, `USAGE`, `ERROR`, and `COMPLETE` stream events

DataHub access uses its Streamable HTTP MCP endpoint and requires the `search`, `get_entities`, and `get_lineage` tools.

## Repository

```text
client/                 Next.js dashboard
server/api/             FastAPI control plane and persistent run API
server/runner/          DataHub and Analytics Agent execution runtime
packages/domain/        Canonical contracts
packages/datahub/       DataHub MCP integration
packages/agents/        Analytics Agent adapter
packages/evaluation/    Deterministic evaluation engine
infra/                  Docker and deployment configuration
tests/                  Unit and integration verification
SPEC.md                 Product and system source of truth
```

## Requirements

- Python 3.11 through 3.14
- Node.js 22 or newer
- pnpm 11.9 or newer
- A DataHub MCP endpoint and service-account token
- A configured DataHub Analytics Agent with a warehouse engine

## Install

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
pnpm install
cp .env.example .env
```

## Run

Start PostgreSQL:

```bash
docker compose -f infra/docker/compose.yml up -d postgres
```

Start the API:

```bash
.venv/bin/uvicorn histograph_api.main:app --reload --port 8000
```

Start the client in another terminal:

```bash
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000). Enter a DataHub MCP connection, an Analytics Agent endpoint and engine name, then define and execute an agent test. Connection tokens are redacted before the request is persisted.

To run PostgreSQL and the API entirely through Docker:

```bash
docker compose -f infra/docker/compose.yml up --build
```

## Verify

```bash
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
.venv/bin/python -m pytest -q -p no:cacheprovider
pnpm typecheck
pnpm build
```

## Evaluation contracts

An agent test can require or forbid:

- DataHub asset URNs consulted by the agent
- SQL tables and columns
- result columns, row ranges, and null limits
- phrases in the final answer

SQL is parsed into a dialect-aware syntax tree with `sqlglot`. Write operations are rejected, and formatting differences do not affect table or column checks.

## Configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `HISTOGRAPH_DATABASE_URL` | `postgresql+asyncpg://histograph:histograph@localhost:5432/histograph` | SQLAlchemy database URL |
| `HISTOGRAPH_ALLOWED_ORIGINS` | `["http://localhost:3000", "http://127.0.0.1:3000"]` | Browser origins allowed by the API |
| `NEXT_PUBLIC_HISTOGRAPH_API_URL` | `http://localhost:8000` | API used by the dashboard |

## License

Apache License 2.0. See [LICENSE](LICENSE).
