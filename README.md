# Histograph

Histograph is continuous assurance for DataHub-powered analytics agents. It detects when code or organizational metadata changes cause an agent to return a successful-looking but semantically wrong answer.

Histograph uses DataHub schemas, lineage, ownership, and documentation to select the protected business questions affected by a change. It then invokes the real analytics agent, records its DataHub tool use, SQL, result shape, and final response, applies deterministic assertions, and publishes an auditable result to Histograph, GitHub, and DataHub.

## How a run works

```text
GitHub, DataHub, schedule, API, or manual trigger
                         │
                         ▼
               Durable Temporal workflow
                         │
                         ▼
        Changed files and DataHub asset lineage
                         │
                         ▼
          Affected protected questions selected
                         │
                         ▼
     DataHub context loaded through MCP for each test
                         │
                         ▼
      Configured Analytics Agent invoked over its API
                         │
                         ▼
 Tool calls, SQL, results, and final answer captured
                         │
                         ▼
       Deterministic contracts evaluated and stored
                         │
                         ▼
 GitHub Check updated and live DataHub incident reconciled
```

Every run records the exact protected-question version, approved baseline, selected dependencies, context evidence, agent events, evaluation findings, and terminal report. Large evidence is content-addressed in S3-compatible object storage; transactional state and audit history remain in PostgreSQL.

## What is implemented

- Multi-tenant organizations and projects with role-based authorization.
- Bootstrap, project-scoped service-token, and OIDC bearer authentication.
- Envelope-encrypted DataHub and agent credentials with key identifiers for rotation.
- DataHub MCP verification and use of `search`, `get_entities`, and `get_lineage`.
- DataHub GraphQL verification and idempotent incident raise, update, resolve, and reopen operations.
- DataHub Analytics Agent health checks, conversation creation, and SSE event capture.
- Versioned suites, protected questions, assertions, baseline capture, proposal, and approval.
- Metadata-aware impact planning based on changed asset URNs, downstream lineage, and approved baseline dependencies.
- Deterministic asset, SQL, result, and response evaluation with read-only SQL enforcement.
- Temporal workflows with retry policies, heartbeats, schedules, cancellation, supersession, and terminal failure persistence.
- GitHub App installation and repository mapping, signed webhook verification, delivery idempotency, pull-request and push triggers, and Check Run reporting.
- Metadata-event ingestion with durable receipts and idempotent run creation.
- PostgreSQL migrations, audit events, soft deletion, tenant constraints, and run idempotency.
- S3-compatible evidence storage and a server-rendered Next.js operations dashboard.
- A complete Docker Compose topology for PostgreSQL, Temporal, MinIO, API, worker, migrations, dashboard, and Temporal UI.

The deployable execution mode is managed execution: the worker must be able to reach DataHub and the Analytics Agent over approved network routes. The public API rejects private-runner configuration until a runner enrollment and job-claim protocol is present.

## Repository

```text
client/                 Next.js dashboard and authenticated server-side API proxy
server/api/             FastAPI control plane, authentication, routes, and migrations
server/runner/          DataHub and Analytics Agent execution runtime
server/worker/          Temporal activities and DataHub incident coordination
packages/domain/        Canonical execution contracts
packages/datahub/       DataHub MCP and GraphQL clients
packages/agents/        DataHub Analytics Agent adapter
packages/evaluation/    Deterministic evaluation engine
packages/github/        GitHub App authentication, API, and webhook security
packages/security/      Envelope encryption and service-token primitives
packages/storage/       S3-compatible evidence storage
packages/workflows/     Temporal workflow definitions and payloads
infra/docker/           Container images and the complete local topology
tests/                  Unit and PostgreSQL integration verification
SPEC.md                 Product behavior and architecture source of truth
```

Python modules use the `histograph_*` package namespace. TypeScript files use kebab-case filenames and `@/...` imports inside the client.

## Local deployment

### Requirements

- Docker Engine with Compose
- Python 3.11 through 3.14 for host-side development and tests
- Node.js 22 and pnpm 11.9 for host-side dashboard development
- A DataHub deployment with MCP enabled
- A DataHub Analytics Agent reachable from the worker

### Configure secrets

```bash
cp .env.example .env
openssl rand -base64 32
openssl rand -hex 32
openssl rand -hex 32
openssl rand -hex 32
```

Use the generated values for:

- `HISTOGRAPH_ENCRYPTION_KEYS=local-v1:<base64-32-byte-key>`
- `HISTOGRAPH_TOKEN_PEPPER=<random-value>`
- `HISTOGRAPH_BOOTSTRAP_TOKEN=<random-value>`
- `HISTOGRAPH_S3_SECRET_ACCESS_KEY=<random-value>`

Do not commit `.env`. The encryption-key setting accepts a comma-separated key ring. The first key encrypts new credentials; retained keys decrypt older ciphertext during rotation.

### Start the complete system

```bash
docker compose --env-file .env -f infra/docker/compose.yml up --build -d
docker compose --env-file .env -f infra/docker/compose.yml ps
```

The migration container must exit successfully before the API and worker start. The default local endpoints are:

| Service | URL |
| --- | --- |
| Histograph | `http://localhost:3000` |
| API and OpenAPI | `http://localhost:8000/docs` |
| Temporal UI | `http://localhost:8080` |
| MinIO API | `http://localhost:9000` |
| MinIO console | `http://localhost:9001` |

Every exposed host port can be changed in `.env` without changing container-to-container addresses.

### Stop the system

```bash
docker compose --env-file .env -f infra/docker/compose.yml down
```

Named PostgreSQL, Temporal, and evidence volumes are retained. Removing volumes deletes local state and is therefore intentionally not part of the standard command.

## Product setup

1. Open the dashboard and create an organization and project.
2. Connect DataHub with its base URL, Streamable HTTP MCP URL, and service-account token.
3. Verify the connection. Histograph requires `search`, `get_entities`, and `get_lineage`, and also verifies the GraphQL actor used for incident writeback.
4. Register and verify the DataHub Analytics Agent endpoint and engine name.
5. Create a suite and a protected question with asset, SQL, result, and response assertions.
6. Run baseline capture. Histograph executes the question and proposes a baseline only from a passing execution.
7. Review and approve the proposed baseline.
8. Add schedules, connect a GitHub repository, ingest metadata events, or run questions manually.

A normal protected run will not silently proceed when required context, an executable version, or an approved baseline is missing. It stops in `action_required` with the missing evidence recorded.

## GitHub App

Configure these variables together:

- `HISTOGRAPH_GITHUB_APP_ID`
- `HISTOGRAPH_GITHUB_PRIVATE_KEY`
- `HISTOGRAPH_GITHUB_WEBHOOK_SECRET`
- `HISTOGRAPH_GITHUB_INSTALL_URL`
- `HISTOGRAPH_PUBLIC_APP_URL`

The GitHub App needs these repository permissions:

- Checks: read and write
- Contents: read
- Metadata: read
- Pull requests: read

Subscribe the app to `installation`, `installation_repositories`, `repository`, `pull_request`, and `push`. Point the webhook to:

```text
https://<api-host>/v1/webhooks/github
```

For each configured pull request or protected-branch push, Histograph verifies the webhook signature, persists the delivery receipt, obtains changed files from GitHub, maps file patterns to DataHub URNs, traverses lineage, and creates or resumes one idempotent Check Run for the exact head SHA. A newer pull-request commit cancels older in-flight work for that pull request.

## DataHub integration

The DataHub token must be able to:

- access the MCP endpoint;
- call `search`, `get_entities`, and `get_lineage`;
- identify its actor through GraphQL;
- raise and update incidents when production incident writeback is enabled.

Histograph does not duplicate DataHub ingestion. Metadata changes arrive through `POST /v1/projects/{project_id}/metadata-events`, or through a bridge consuming the organization's DataHub event source. The event is persisted with its source identifier, mapped to changed URNs, and passed into the same workflow used by GitHub and scheduled runs.

Live failures are deduplicated by protected question and affected resource. Failed DataHub writes remain pending and are retried without creating a second local incident. Repeated passing runs resolve the incident; a later regression reopens the same Histograph-owned incident.

## Authentication and security

Local Compose uses the bootstrap token only through the dashboard's server-side proxy. The token is not compiled into browser JavaScript.

For deployed API access, configure `HISTOGRAPH_OIDC_ISSUER` and `HISTOGRAPH_OIDC_AUDIENCE` together. OIDC users are matched to organization memberships and roles. Project-scoped service identities support only the declared `control-plane:write` and `metadata-events:write` scopes and cannot create organizations or cross tenant boundaries.

The managed dashboard should be placed behind the organization's authenticated ingress. Its server-side `HISTOGRAPH_API_TOKEN` must be stored as a deployment secret and scoped to the operations the dashboard is allowed to perform. Never expose that value through a `NEXT_PUBLIC_*` variable.

Production deployments should use managed PostgreSQL, Temporal, and S3 services, TLS for every external route, a secret manager for the key ring and integration credentials, network policy limiting worker egress, database backups, object-retention policy, and the OIDC configuration above. The Compose file is a complete reproducible single-host topology, not a high-availability production topology.

## Host development

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
pnpm install --frozen-lockfile
```

Apply migrations before starting the API:

```bash
.venv/bin/alembic upgrade head
.venv/bin/uvicorn histograph_api.main:app_factory --factory --reload --port 8000
```

In separate terminals:

```bash
.venv/bin/python -m histograph_worker.main
pnpm dev
```

## Verification

Create a separate `histograph_test` PostgreSQL database, then run:

```bash
HISTOGRAPH_TEST_DATABASE_URL=postgresql+asyncpg://histograph:histograph@localhost:5432/histograph_test .venv/bin/python -m pytest -q -p no:cacheprovider
.venv/bin/python -m ruff format --check .
.venv/bin/python -m ruff check .
pnpm typecheck
pnpm build
.venv/bin/alembic check
```

CI also performs a full migration upgrade, schema-drift check, downgrade to base, re-upgrade, Python tests, dashboard production build, and all three application container builds.

## License

Apache License 2.0. See [LICENSE](LICENSE).
