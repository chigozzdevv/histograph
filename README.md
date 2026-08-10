# Histograph

Histograph is a production ML incident-response platform. It receives model predictions, delayed outcomes, and deployment events; detects deterministic abnormalities; investigates them through DataHub lineage; coordinates approved remediation; and verifies recovery.

The implemented headless runtime uses Postgres for control-plane state and ClickHouse for
high-volume observations. The API receives events and approvals; a separate worker process runs
scheduled detection, DataHub investigation, approved actions, and recovery verification.

## Local services

The repository compose file starts the Histograph dependencies without touching any other Docker project:

```bash
./scripts/compose.sh up -d postgres clickhouse redis
```

Install the Python environment, including the reproducible reference-model dependencies, and run
the checks:

```bash
uv sync --dev --extra demo
./scripts/check.sh
```

With Postgres and ClickHouse running, execute the database-backed API flow as well:

```bash
HISTOGRAPH_RUN_INTEGRATION=1 uv run pytest server/tests/integration
```

Run the API after the services are healthy:

```bash
uv run uvicorn histograph.api.main:app --app-dir server/src --reload
```

Run the continuous control-plane worker in a separate terminal. It uses PostgreSQL leases and
`FOR UPDATE SKIP LOCKED`, so multiple worker replicas do not evaluate the same due monitor or
execute the same approved action concurrently:

```bash
PYTHONPATH=server/src uv run python -m histograph.workers
```

The API is available at `http://localhost:8000`. Startup applies checksummed Postgres and ClickHouse migrations before accepting traffic.

The headless flow is:

1. Register the model and its binary-class semantics at `/v1/models/{model_name}`.
2. Send predictions, outcomes, deployment events, or upstream change events to the matching
   `/v1/events/*` endpoint. Prediction and outcome endpoints support batches of up to 5,000 events.
3. Create a versioned monitor at `/v1/monitors`. Feature-drift monitors store `feature`; canary
   monitors store `reference_version`; all monitors store `check_interval_seconds`.
4. The worker claims due monitors, records every run, opens deduplicated incidents, and performs the
   DataHub investigation automatically. `/v1/detection/*` remains available for deterministic
   replay and diagnosis, but it is not required for continuous operation.
5. A `probable_cause` investigation proposes a deduplicated protective action. It does not wait for
   `confirmed_cause`, because that status is reserved for recovery verified after the action.
6. An authorized engineer approves or rejects the proposal. A provider-neutral webhook can execute
   an approved action directly. For an imported GitOps deployment, Histograph instead opens a
   rollback pull request and the signed merge becomes the approval.
7. The worker verifies independent deployment/change state and fresh monitor evidence, reinvestigates
   to reach `confirmed_cause`, optionally writes the result to DataHub, and only then resolves the
   incident.

The implemented performance evaluator supports binary classification with an explicit positive
prediction class and actual-outcome value. The implemented drift evaluator supports numeric-feature
PSI. Monitor creation rejects signal and metric combinations that are not implemented yet, and each
monitor requires a minimum sample size before it can trigger an incident.

An investigation reads the model entity and both directions of its DataHub lineage through MCP, records the exact tool trace and lineage evidence on the incident, and keeps the incident open until a dependency change is corroborated. Set `HISTOGRAPH_DATAHUB_MCP_MUTATIONS_ENABLED=true` and pass `write_back: true` only when the team has approved saving the investigation as a DataHub analysis document.

An incident can enter `resolved` only after persisted recovery evidence contains the action result,
independent runtime state, and fresh health proof required for that action. Adapter success alone is
not recovery. A stopped canary requires a later deployment event showing zero candidate traffic and
a fresh labeled performance window for the stable version; a full model rollback requires the old
version to stop plus fresh labeled traffic on the declared rollback version; an upstream rollback
requires a rollback change event and a fresh healthy monitor window. A responsible engineer can
instead set the incident to `closed`, but manual closure requires a reason and is recorded separately
in the timeline.

## Approval-driven remediation

Approver identity comes from a configured bearer token, not from request-body actor fields. For a
local environment, configure token-to-identity mappings and the organization-owned remediation
webhook:

```bash
export HISTOGRAPH_APPROVAL_TOKENS='{"local-approver-token":"risk-lead@example.com"}'
export HISTOGRAPH_REMEDIATION_WEBHOOK_URL=https://automation.example.com/histograph/actions
export HISTOGRAPH_REMEDIATION_WEBHOOK_TOKEN=<outbound-token>
export HISTOGRAPH_REMEDIATION_CALLBACK_TOKEN=<callback-token>
```

Approve an action with `POST /v1/actions/{action_id}/approval` and a bearer token. The webhook
receives the immutable action ID as its `Idempotency-Key` and a JSON body containing `action_id`,
`action_type`, `target`, and `evidence`. It returns:

```json
{
  "status": "accepted",
  "external_execution_id": "provider-run-123",
  "details": {}
}
```

`accepted` remains `executing`; it is not success. The provider later calls
`POST /v1/actions/{action_id}/result` with the callback bearer token and a terminal `succeeded` or
`failed` result. Providers that finish synchronously can return a terminal status immediately.
Monitor history is available at `/v1/monitors/{monitor_id}/runs`, and action approval, execution,
failure, and recovery history is available at `/v1/actions/{action_id}`.

## GitHub GitOps deployments

GitHub is the desired-state and approval system; it is not treated as proof of runtime state.
Histograph imports an explicit `ModelDeployment` manifest, registers the manifest's model and
DataHub URN, and keeps desired Git state separate from deployment/change events observed from the
serving runtime.

The reference manifest is
[`.histograph/deployments/mobile-money-fraud.yaml`](.histograph/deployments/mobile-money-fraud.yaml).
It declares the stable and candidate artifacts, traffic percentages, decision-threshold
configuration, DataHub identity, and explicit rollback targets. Histograph refuses to generate a
rollback when the action target does not match the imported deployment or the manifest does not
declare the required previous version.

Configure the GitHub App integration:

```bash
export HISTOGRAPH_GITHUB_APP_ID=<app-id>
export HISTOGRAPH_GITHUB_APP_PRIVATE_KEY_PATH=/absolute/path/to/github-app.pem
export HISTOGRAPH_GITHUB_WEBHOOK_SECRET=<webhook-secret>
export HISTOGRAPH_GITHUB_CONFIGURATION_TOKEN=<configuration-token>
```

The App needs access only to selected deployment repositories. The implemented operations require
repository **Contents: read/write**, **Pull requests: read/write**, and **Deployments: read/write**
permissions; GitHub supplies Metadata read access. Subscribe its webhook to `push`, `pull_request`,
and `deployment_status` events at `POST /v1/integrations/github/webhook`. The webhook URL must be a
public HTTPS URL that forwards to that route; the HMAC secret is verified against the unmodified
request body.

The configuration token protects the headless setup APIs:

```text
POST /v1/integrations/github/connections
POST /v1/integrations/github/connections/{connection_id}/sync
GET  /v1/integrations/github/connections
GET  /v1/integrations/github/deployments
```

When a probable cause targets an imported deployment, the continuous worker opens a normal rollback
PR on a deterministic `histograph/rollback-<action-id>` branch. The action remains `proposed` while
the PR is open. A signed merged-PR webhook records the GitHub actor as the approver and moves the
action to `executing`; closing without merge rejects it. A matching GitHub deployment status marks
execution succeeded or failed, but recovery still requires a later runtime deployment/change event
and the existing deterministic verification. The merged `push` re-imports the manifest so desired
and observed state can return to `in_sync`.

### Reference serving and reconciliation

The separate reference runtime makes the demo operational without turning Histograph itself into a
deployment provider. It loads the trained artifact declared by the manifest, applies the explicit
feature and threshold configuration, routes stable/candidate traffic with a deterministic hash,
serves predictions, accepts delayed outcomes, and sends runtime evidence through a durable SQLite
outbox. Manifest state and its deployment/change evidence commit atomically.

Configure a non-public control token and start it:

```bash
export HISTOGRAPH_REFERENCE_CONTROL_TOKEN=<random-runtime-control-token>
PYTHONPATH=server/src uv run --extra demo python -m demo.runtime
```

The reference reconciler polls the selected repository, creates a GitHub Deployment for a new
revision, applies that exact revision to the runtime, and reports `in_progress`, `success`, or
`failure` through GitHub. Its success webhook completes execution in Histograph; the runtime's
separate deployment events prove what is actually serving.

```bash
export HISTOGRAPH_REFERENCE_GITHUB_INSTALLATION_ID=<installation-id>
export HISTOGRAPH_REFERENCE_GITHUB_REPOSITORY_OWNER=<owner>
export HISTOGRAPH_REFERENCE_GITHUB_REPOSITORY_NAME=<repository>
export HISTOGRAPH_REFERENCE_GITHUB_BRANCH=main
export HISTOGRAPH_REFERENCE_GITHUB_MANIFEST_PATH=.histograph/deployments/mobile-money-fraud.yaml
PYTHONPATH=server/src uv run --extra demo python -m demo.runtime.reconcile
```

Create and import the headless connection once the App is installed:

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

Then call `POST /v1/integrations/github/connections/{connection_id}/sync`. Start the API, control
plane worker, reference runtime, and reference reconciler as four independent processes. No manual
detection or investigation call is needed; scheduled monitors drive that path.

## Repository contract and client API

The canonical demo deployment lives at
[`.histograph/deployments/mobile-money-fraud.yaml`](.histograph/deployments/mobile-money-fraud.yaml)
and references repository-relative JSON Schemas and checked-in examples:

```text
.histograph/
├── deployments/mobile-money-fraud.yaml
├── schemas/mobile-money-fraud-input.schema.json
├── schemas/mobile-money-fraud-output.schema.json
└── examples/mobile-money-fraud.yaml
```

GitHub sync resolves all three resources at the same repository revision and stores their validated
contents with the imported deployment. Paths that escape the repository are rejected. The browser
never reads GitHub, DataHub, or the model runtime directly.

The client-ready read and playground surface is:

```text
GET  /v1/overview
GET  /v1/deployments
GET  /v1/deployments/{deployment_id}
POST /v1/deployments/{deployment_id}/predict
POST /v1/deployments/{deployment_id}/compare
GET  /v1/monitors
GET  /v1/activity
GET  /v1/integrations
```

Playground inputs are validated against the imported Draft 2020-12 JSON Schema. Runtime endpoints
must use HTTP(S), cannot embed credentials, and must match `HISTOGRAPH_PLAYGROUND_ALLOWED_HOSTS`.
`compare` uses the server-held runtime control token and intentionally emits no prediction telemetry,
so interactive comparisons cannot pollute production monitors. Prediction and comparison calls use
a database-backed per-client rate limit that remains consistent across API replicas.

## Controlled public demo

`POST /v1/demo/scenarios` creates one durable controlled run for an imported deployment. The normal
worker emits held-out canary traffic and then tracks the existing monitor, investigation, GitHub PR,
execution, and recovery records through these stages:

```text
queued → emitting_traffic → monitoring → investigating → awaiting_approval
       → remediating → emitting_recovery_traffic → verifying → resolved
```

Use `GET /v1/demo/scenarios/{run_id}` to poll progress. Only one run can be active, including across
worker replicas. By default, starting and resetting a run require
`Authorization: Bearer $HISTOGRAPH_DEMO_CONTROL_TOKEN`. A hosted self-service environment may set
`HISTOGRAPH_DEMO_PUBLIC_SCENARIOS_ENABLED=true`; the database-level single-run guard still applies.
Public starts also use a separate hourly per-client rate limit.

After the reconciler removes candidate traffic, the durable demo worker replays labeled held-out
rows through the recovered runtime. Recovery remains pending until the stable version has enough
strictly post-remediation prediction/outcome pairs and its performance passes against the incident's
original same-window reference value.

After recovery is verified, `POST /v1/demo/scenarios/{run_id}/reset` opens an idempotent GitHub PR
that restores the exact pre-scenario canary manifest. It never rewrites Git state or serving state
directly.

## Remote demo packaging

Training now exports a compact 10,000-row held-out `replay.parquet` beside the model artifact. The
container workflow rebuilds both from the pinned, checksummed dataset and publishes one image to
GHCR. The same immutable image runs the API, worker, reference runtime, and reconciler with separate
commands.

[`compose.demo.yaml`](compose.demo.yaml) keeps Postgres, ClickHouse, the runtime control endpoint,
and the reconciler private. Caddy exposes only the Histograph API over HTTP/HTTPS. For a remote host:

```bash
export HISTOGRAPH_IMAGE=ghcr.io/<owner>/<repository>@sha256:<published-digest>
export HISTOGRAPH_DEMO_SITE_ADDRESS=histograph.ai
docker compose -f compose.demo.yaml up -d
```

Before starting the full GitOps services, configure:

- `HISTOGRAPH_GITHUB_APP_ID`, `HISTOGRAPH_GITHUB_APP_PRIVATE_KEY`, and
  `HISTOGRAPH_GITHUB_WEBHOOK_SECRET`;
- the reference installation ID, repository owner, and repository name;
- independent GitHub configuration, runtime control, and demo control tokens;
- the reachable DataHub GMS URL/token and whether explicit write-back is enabled.

No public demo visitor receives or enters those credentials.

## Reference fraud environment

The runnable reference environment is in [`demo/README.md`](demo/README.md). It uses a credited,
CC BY 4.0 synthetic mobile-money transaction dataset, a chronological split with explicit
label-delay gaps, two model candidates, a held-out controlled replay, and viability gates that stop
weak scenarios from being presented.

It demonstrates two distinct release failures:

1. A feature release silently scales `amount` by 100. Histograph measures PSI, reports the largest
   directional performance loss in percentage points and relative percent, uses DataHub lineage to
   constrain the suspected change, and confirms causality only after rollback and verified replay
   recovery.
2. A 10% model canary ships an incorrect decision threshold. Histograph compares v2 against v1 on
   the same rows and time window, attributes the regression to the candidate deployment, and keeps
   the incident unresolved until candidate traffic is removed and recovery is recorded.

The production Histograph control plane observes models; it does not choose customer models or
become their deployment provider. The repository's separate reference runtime hosts only this
reproducible demo and proves the connector contract. Histograph coordinates an explicitly approved
rollback through the organization's configured adapter.

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
export HISTOGRAPH_DATAHUB_MCP_TIMEOUT_SECONDS=120
```

The local DataHub quickstart is separate from the Histograph compose project so its own dependencies and lifecycle remain isolated.
