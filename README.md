# Histograph

Histograph is a production ML incident-response platform. It receives model predictions, delayed
outcomes, deployment events, and upstream changes; detects deterministic regressions; investigates
them through DataHub lineage; coordinates approved remediation; and verifies recovery before
resolving an incident.

## How It Works

1. Histograph receives predictions, delayed outcomes, and deployment events.
2. A continuous monitor detects a model regression.
3. DataHub lineage connects the affected model to its features, datasets, owners, and consumers.
4. Histograph correlates that context with release evidence to identify a probable cause.
5. Histograph opens a rollback pull request for the affected deployment.
6. An engineer reviews and merges the pull request.
7. The deployment reconciler applies the approved change.
8. Histograph evaluates fresh post-remediation predictions and outcomes.
9. The incident is resolved only after recovery is verified, and the evidence is saved to DataHub.

Histograph keeps detection, investigation, remediation, and recovery separate:

- `probable_cause` means the evidence is sufficient to propose a protective action.
- `confirmed_cause` means recovery was verified after reversing the suspected change.
- `resolved` means Histograph verified recovery using fresh post-remediation evidence.
- `closed` means an engineer manually closed the incident with a recorded reason.

## Dataset Credit

The reference environment uses:

Azamuke, Denish (2024), *Synthetic Mobile Money Transaction Dataset*, Mendeley Data, Version 2.

DOI: [10.17632/zhj366m53p.2](https://doi.org/10.17632/zhj366m53p.2)

License: [Creative Commons Attribution 4.0](https://creativecommons.org/licenses/by/4.0/)

The repository does not redistribute the source dataset. Its preparation pipeline preserves the
source version, citation, and file checksums.

## Architecture

Histograph runs as a set of independent control-plane components:

- **FastAPI API** receives model, prediction, outcome, deployment, change, and approval events.
- **Continuous worker** evaluates monitors, opens incidents, runs investigations, proposes actions,
  and verifies recovery.
- **Postgres** stores models, monitors, incidents, approvals, actions, deployment state, and demo
  runs.
- **ClickHouse** stores high-volume prediction and outcome observations.
- **DataHub MCP Server** provides model, feature, dataset, ownership, and lineage context.
- **GitHub App** imports deployment manifests and opens rollback pull requests.
- **Reference runtime** serves the reproducible fraud model and emits runtime evidence.
- **Reconciler** applies merged Git configuration and reports deployment status.

GitHub represents desired deployment state. A merged pull request is not treated as proof of
recovery: the serving runtime must independently report the new state, followed by fresh healthy
predictions and outcomes.

## Local Setup

### Requirements

- Python 3.13
- [`uv`](https://docs.astral.sh/uv/)
- Docker with Compose

Install the project and reference-model dependencies:

```bash
uv sync --dev --extra demo
```

Start Postgres, ClickHouse, and Redis without affecting other Docker projects:

```bash
./scripts/compose.sh up -d postgres clickhouse redis
```

Run static checks and unit tests:

```bash
./scripts/check.sh
```

Run the database-backed integration suite:

```bash
HISTOGRAPH_RUN_INTEGRATION=1 uv run pytest server/tests/integration
```

Start the API:

```bash
uv run uvicorn histograph.api.main:app --app-dir server/src --reload
```

Start the continuous worker in another terminal:

```bash
PYTHONPATH=server/src uv run python -m histograph.workers
```

The API is available at `http://localhost:8000`. Startup applies checksummed Postgres and
ClickHouse migrations before accepting traffic.

## DataHub Integration

Histograph connects to self-hosted DataHub OSS through the official DataHub MCP Server. Each
registered model is associated with a DataHub ML model URN.

During an investigation, Histograph:

1. Derives the DataHub URN from the registered model.
2. Fetches the model entity through MCP.
3. Traverses upstream and downstream lineage.
4. Collects connected features, datasets, owners, and consumers.
5. Correlates lineage with deployment and upstream-change events.
6. Stores the MCP tool trace and supporting evidence on the incident.
7. Writes the final investigation and verified recovery evidence back to DataHub.

DataHub narrows the investigation to relevant organizational context. Lineage alone is not treated
as proof of causality; Histograph still requires correlated release evidence and verified recovery.

### Start DataHub Locally

Bootstrap the pinned DataHub Quickstart environment:

```bash
./infra/datahub/bootstrap.sh
set -a
source infra/datahub/.env
set +a
```

Check GMS, the frontend, and the MCP connection:

```bash
./infra/datahub/health.sh
```

Configure Histograph:

```bash
export HISTOGRAPH_DATAHUB_GMS_URL=http://localhost:8080
export HISTOGRAPH_DATAHUB_FRONTEND_URL=http://localhost:9002
export HISTOGRAPH_DATAHUB_GMS_TOKEN=<token>
export HISTOGRAPH_DATAHUB_MCP_COMMAND=uvx
export HISTOGRAPH_DATAHUB_MCP_PACKAGE=mcp-server-datahub==0.6.0
export HISTOGRAPH_DATAHUB_MCP_PYTHON=3.13
export HISTOGRAPH_DATAHUB_MCP_TIMEOUT_SECONDS=120
```

Stop the local DataHub environment with `./infra/datahub/stop.sh`.

## GitHub GitOps Integration

Organizations install the Histograph GitHub App and grant it access only to selected deployment
repositories. Histograph imports a `ModelDeployment` manifest containing:

- Model identity and DataHub URN
- Stable and candidate versions
- Traffic percentages and decision thresholds
- Artifact locations
- Input and output schemas
- Example inputs
- Feature assets and rollback targets

The reference manifest is
[`.histograph/deployments/mobile-money-fraud.yaml`](.histograph/deployments/mobile-money-fraud.yaml).

Configure the GitHub App:

```bash
export HISTOGRAPH_GITHUB_APP_ID=<app-id>
export HISTOGRAPH_GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/github-app.pem
export HISTOGRAPH_GITHUB_WEBHOOK_SECRET=<webhook-secret>
export HISTOGRAPH_GITHUB_CONFIGURATION_TOKEN=<configuration-token>
```

Required repository permissions are:

- Contents: read and write
- Pull requests: read and write
- Deployments: read and write
- Metadata: read

Subscribe the App to `push`, `pull_request`, and `deployment_status`. The webhook endpoint is:

```text
POST /v1/integrations/github/webhook
```

When an investigation identifies a probable cause, Histograph opens a rollback PR on a
`histograph/rollback-<action-id>` branch. Merging the PR records the GitHub actor as the approver;
closing it without merging rejects the proposed action.

Create and import a repository connection:

```bash
curl -X POST http://localhost:8000/v1/integrations/github/connections \
  -H "Authorization: Bearer ${HISTOGRAPH_GITHUB_CONFIGURATION_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{
    "installation_id": 123,
    "repository_owner": "example",
    "repository_name": "deployments",
    "branch": "main",
    "manifest_path": ".histograph/deployments/mobile-money-fraud.yaml"
  }'
```

Then call `POST /v1/integrations/github/connections/{connection_id}/sync`.

## Reference Runtime and Reconciliation

The reference runtime makes the demo reproducible without turning Histograph into a model-hosting
or deployment provider. It loads the artifact declared by the manifest, applies version-specific
configuration, routes stable and candidate traffic, accepts delayed outcomes, and emits runtime
evidence through a durable SQLite outbox.

Start the runtime:

```bash
export HISTOGRAPH_REFERENCE_CONTROL_TOKEN=<control-token>
PYTHONPATH=server/src uv run --extra demo python -m demo.runtime
```

Configure and start the reconciler:

```bash
export HISTOGRAPH_REFERENCE_GITHUB_INSTALLATION_ID=<installation-id>
export HISTOGRAPH_REFERENCE_GITHUB_REPOSITORY_OWNER=<owner>
export HISTOGRAPH_REFERENCE_GITHUB_REPOSITORY_NAME=<repository>
export HISTOGRAPH_REFERENCE_GITHUB_BRANCH=main
export HISTOGRAPH_REFERENCE_GITHUB_MANIFEST_PATH=.histograph/deployments/mobile-money-fraud.yaml

PYTHONPATH=server/src uv run --extra demo python -m demo.runtime.reconcile
```

The reconciler reads an exact Git revision, applies its manifest to the runtime, and reports
deployment progress through GitHub. Runtime events separately prove what is actually serving.

## Controlled Public Demo

The hosted product is available at [app.histograph.ai](https://app.histograph.ai).

The reference deployment serves a mobile-money fraud model with v1 receiving 90% of traffic and a
v2 canary receiving 10%. Both versions use the same trained artifact, while v2 deliberately uses an
incorrect decision threshold.

Starting the controlled scenario causes the worker to:

1. Replay 1,000 held-out transactions through the real runtime.
2. Submit a delayed outcome for every prediction.
3. Evaluate v2 against v1 in the same time window.
4. Open an incident when v2 recall regresses.
5. Investigate the model and its lineage through DataHub.
6. Open a real GitHub rollback PR.
7. Pause until an engineer merges the PR.
8. Verify that candidate traffic becomes 0%.
9. Replay fresh labeled traffic through the recovered runtime.
10. Resolve the incident only after the stable release passes verification.
11. Save the final investigation and recovery evidence to DataHub.

The Playground's comparison mode does not record telemetry, so interactive comparisons cannot
affect production monitors.

## Repository Deployment Contract

```text
.histograph/
├── deployments/
│   └── mobile-money-fraud.yaml
├── schemas/
│   ├── mobile-money-fraud-input.schema.json
│   └── mobile-money-fraud-output.schema.json
└── examples/
    └── mobile-money-fraud.yaml
```

GitHub sync resolves and validates all resources at the same repository revision. Repository paths
that escape `.histograph` are rejected. The browser never reads GitHub, DataHub, or the model
runtime directly.

## Remote Deployment

Training exports the model artifact, its manifest, and a compact held-out replay dataset. The
container workflow publishes one immutable image that can run the API, worker, reference runtime,
and reconciler with separate commands.

```bash
export HISTOGRAPH_IMAGE=ghcr.io/<owner>/<repository>@sha256:<digest>
export HISTOGRAPH_DEMO_SITE_ADDRESS=histograph.ai
docker compose -f compose.demo.yaml up -d
```

The demo Compose stack keeps Postgres, ClickHouse, the runtime control endpoint, and the reconciler
private. Caddy exposes only the Histograph API.

## Additional References

- [Reference environment](demo/README.md)
- [Model card](demo/MODEL_CARD.md)
- [Deployment manifest](.histograph/deployments/mobile-money-fraud.yaml)
- [Example model inputs](.histograph/examples/mobile-money-fraud.yaml)
- [Environment configuration](.env.example)
- [Third-party notices](THIRD_PARTY_NOTICES.md)

## License

See [LICENSE](LICENSE).
