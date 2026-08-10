import asyncio
import hashlib
import hmac
import json
import os
from collections.abc import Generator
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

import clickhouse_connect
import joblib
import pytest
import yaml
from demo.runtime.service import ReferenceRuntime
from demo.runtime.state import RuntimeStateStore
from demo.runtime.telemetry import TelemetryWorker
from demo.runtime.types import OutcomeRequest, PredictionRequest
from fastapi.testclient import TestClient
from psycopg import connect, sql

from histograph.api.app import create_app
from histograph.detection.service import MonitorEvaluationService
from histograph.integrations.github.types import CreatedPullRequest, GitHubRepositoryFile
from histograph.integrations.github.workers import GitOpsProposalWorker
from histograph.product.runtime import RuntimeConnector
from histograph.remediation.adapters import RemediationAdapter
from histograph.remediation.service import RemediationService
from histograph.remediation.types import ExecutionResult
from histograph.settings import Settings
from histograph.workers.services import (
    ActionWorker,
    InvestigationWorker,
    MonitorWorker,
    RecoveryEvaluator,
    RecoveryWorker,
)

pytestmark = pytest.mark.skipif(
    os.getenv("HISTOGRAPH_RUN_INTEGRATION") != "1",
    reason="Set HISTOGRAPH_RUN_INTEGRATION=1 to run database integration tests",
)


@pytest.fixture
def integration_settings() -> Generator[Settings]:
    suffix = uuid4().hex
    postgres_database = f"histograph_test_{suffix}"
    clickhouse_database = f"histograph_test_{suffix}"
    admin_dsn = "postgresql://histograph:histograph@localhost:5433/postgres"

    with connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(postgres_database)))

    settings = Settings(
        postgres_dsn=(f"postgresql://histograph:histograph@localhost:5433/{postgres_database}"),
        clickhouse_database=clickhouse_database,
        approval_tokens={"integration-approver-token": "risk-lead@example.com"},
        remediation_callback_token="integration-callback-token",
        github_configuration_token="integration-github-config-token",
        github_webhook_secret="integration-github-webhook-secret",
    )
    try:
        yield settings
    finally:
        clickhouse = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
        )
        clickhouse.command(f"DROP DATABASE IF EXISTS {clickhouse_database}")
        clickhouse.close()
        with connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(postgres_database)
                )
            )


def test_binary_monitor_creates_one_auditable_incident(
    integration_settings: Settings,
) -> None:
    with TestClient(create_app(integration_settings)) as client:
        model_response = client.put(
            "/v1/models/fraud",
            json={
                "name": "fraud",
                "task": "binary_classification",
                "positive_class": "blocked",
                "positive_actual": "chargeback",
            },
        )
        assert model_response.status_code == 200

        deployment_response = client.post(
            "/v1/events/deployments",
            json={
                "deployment": "fraud-production",
                "model": "fraud",
                "version": "v1",
                "status": "active",
                "occurred_at": "2026-08-08T10:00:00Z",
            },
        )
        assert deployment_response.status_code == 202

        events = [
            (
                "baseline-1",
                "blocked",
                "chargeback",
                "2026-08-08T11:00:00Z",
                "2026-08-08T11:20:00Z",
            ),
            (
                "baseline-2",
                "allowed",
                "legitimate",
                "2026-08-08T11:10:00Z",
                "2026-08-08T11:21:00Z",
            ),
            (
                "current-1",
                "blocked",
                "legitimate",
                "2026-08-08T11:50:00Z",
                "2026-08-08T11:55:00Z",
            ),
            (
                "current-2",
                "allowed",
                "legitimate",
                "2026-08-08T11:51:00Z",
                "2026-08-08T11:56:00Z",
            ),
        ]
        for prediction_id, predicted_class, actual, observed_at, actual_at in events:
            prediction_response = client.post(
                "/v1/events/predictions",
                json={
                    "prediction_id": prediction_id,
                    "model": "fraud",
                    "version": "v1",
                    "observed_at": observed_at,
                    "predicted_class": predicted_class,
                },
            )
            assert prediction_response.status_code == 202
            actual_response = client.post(
                "/v1/events/actuals",
                json={
                    "prediction_id": prediction_id,
                    "actual": actual,
                    "observed_at": actual_at,
                },
            )
            assert actual_response.status_code == 202

        monitor_response = client.post(
            "/v1/monitors",
            json={
                "model": "fraud",
                "signal": "performance",
                "metric": "accuracy",
                "operator": "lt",
                "threshold": 0.75,
                "minimum_sample_size": 2,
            },
        )
        assert monitor_response.status_code == 201
        monitor_id = monitor_response.json()["id"]

        payload = {"as_of": "2026-08-08T12:00:00Z"}
        first_detection = client.post(
            f"/v1/detection/monitors/{monitor_id}/performance",
            json=payload,
        )
        assert first_detection.status_code == 200
        assert first_detection.json()["status"] == "evaluated"
        assert first_detection.json()["observed_value"] == 0.5
        assert first_detection.json()["triggered"] is True
        incident_id = first_detection.json()["incident_id"]

        repeated_detection = client.post(
            f"/v1/detection/monitors/{monitor_id}/performance",
            json=payload,
        )
        assert repeated_detection.status_code == 200
        assert repeated_detection.json()["incident_id"] == incident_id

        incident_response = client.get(f"/v1/incidents/{incident_id}")
        assert incident_response.status_code == 200
        assert incident_response.json()["status"] == "open"
        assert [event["event_type"] for event in incident_response.json()["timeline"]] == [
            "created"
        ]

        premature_resolution = client.patch(
            f"/v1/incidents/{incident_id}",
            json={"status": "resolved"},
        )
        assert premature_resolution.status_code == 409
        assert premature_resolution.json()["detail"] == (
            "Incident cannot be resolved until recovery has been verified"
        )

        close_without_reason = client.patch(
            f"/v1/incidents/{incident_id}",
            json={"status": "closed"},
        )
        assert close_without_reason.status_code == 422

        manual_close = client.patch(
            f"/v1/incidents/{incident_id}",
            json={"status": "closed", "reason": "Model mapping corrected"},
        )
        assert manual_close.status_code == 200
        assert manual_close.json()["status"] == "closed"
        assert manual_close.json()["resolved_at"] is not None


def test_feature_drift_detects_a_shift_from_a_constant_baseline(
    integration_settings: Settings,
) -> None:
    with TestClient(create_app(integration_settings)) as client:
        model_response = client.put(
            "/v1/models/fraud",
            json={
                "name": "fraud",
                "task": "binary_classification",
                "positive_class": "blocked",
                "positive_actual": "chargeback",
            },
        )
        assert model_response.status_code == 200

        predictions = [
            ("baseline-1", 1.0, "2026-08-08T11:00:00Z"),
            ("baseline-2", 1.0, "2026-08-08T11:10:00Z"),
            ("current-1", 10.0, "2026-08-08T11:50:00Z"),
            ("current-2", 10.0, "2026-08-08T11:51:00Z"),
        ]
        for prediction_id, feature_value, observed_at in predictions:
            response = client.post(
                "/v1/events/predictions",
                json={
                    "prediction_id": prediction_id,
                    "model": "fraud",
                    "version": "v1",
                    "observed_at": observed_at,
                    "features": {"merchant_velocity": feature_value},
                },
            )
            assert response.status_code == 202

        monitor_response = client.post(
            "/v1/monitors",
            json={
                "model": "fraud",
                "version": "v1",
                "signal": "feature_drift",
                "metric": "psi",
                "feature": "merchant_velocity",
                "operator": "gt",
                "threshold": 0.2,
                "minimum_sample_size": 2,
            },
        )
        assert monitor_response.status_code == 201
        monitor_id = monitor_response.json()["id"]

        detection_response = client.post(
            f"/v1/detection/monitors/{monitor_id}/feature-drift",
            json={
                "as_of": "2026-08-08T12:00:00Z",
            },
        )

        assert detection_response.status_code == 200
        assert detection_response.json()["status"] == "evaluated"
        assert detection_response.json()["triggered"] is True
        assert detection_response.json()["observed_value"] > 0.2
        assert detection_response.json()["incident_id"] is not None


def test_canary_comparison_change_ingestion_and_verified_recovery(
    integration_settings: Settings,
) -> None:
    with TestClient(create_app(integration_settings)) as client:
        assert (
            client.put(
                "/v1/models/fraud-canary",
                json={
                    "name": "fraud-canary",
                    "task": "binary_classification",
                    "positive_class": "blocked",
                    "positive_actual": "chargeback",
                    "datahub_urn": "urn:li:mlModel:fraud-canary",
                },
            ).status_code
            == 200
        )
        for version, status, traffic in (("v1", "active", 90), ("v2", "monitoring", 10)):
            assert (
                client.post(
                    "/v1/events/deployments",
                    json={
                        "deployment": "fraud-canary-production",
                        "model": "fraud-canary",
                        "version": version,
                        "strategy": "canary",
                        "traffic_percentage": traffic,
                        "status": status,
                        "occurred_at": "2026-08-08T11:40:00Z",
                    },
                ).status_code
                == 202
            )

        prediction_events = []
        actual_events = []
        reference_predictions = ["blocked", "blocked", "allowed", "allowed"]
        candidate_predictions = ["blocked", "allowed", "allowed", "allowed"]
        labels = ["chargeback", "chargeback", "legitimate", "legitimate"]
        for version, predicted_classes in (
            ("v1", reference_predictions),
            ("v2", candidate_predictions),
        ):
            for index, (predicted_class, actual) in enumerate(
                zip(predicted_classes, labels, strict=True)
            ):
                prediction_id = f"{version}-{index}"
                prediction_events.append(
                    {
                        "prediction_id": prediction_id,
                        "model": "fraud-canary",
                        "version": version,
                        "deployment": "fraud-canary-production",
                        "observed_at": f"2026-08-08T11:5{index}:00Z",
                        "predicted_class": predicted_class,
                    }
                )
                actual_events.append(
                    {
                        "prediction_id": prediction_id,
                        "actual": actual,
                        "observed_at": f"2026-08-08T11:5{index}:30Z",
                    }
                )
        predictions = client.post(
            "/v1/events/predictions/batch", json={"events": prediction_events}
        )
        actuals = client.post("/v1/events/actuals/batch", json={"events": actual_events})
        assert predictions.status_code == 202
        assert predictions.json()["count"] == 8
        assert actuals.status_code == 202
        assert actuals.json()["count"] == 8

        change = client.post(
            "/v1/events/changes",
            json={
                "asset_urn": "urn:li:mlModel:fraud-canary",
                "asset_name": "fraud-canary",
                "asset_type": "model",
                "version": "v2",
                "change_type": "configuration",
                "status": "applied",
                "occurred_at": "2026-08-08T11:40:00Z",
                "metadata": {"threshold": 0.9},
            },
        )
        assert change.status_code == 202

        monitor = client.post(
            "/v1/monitors",
            json={
                "model": "fraud-canary",
                "version": "v2",
                "reference_version": "v1",
                "deployment": "fraud-canary-production",
                "signal": "performance",
                "metric": "recall",
                "operator": "decrease",
                "threshold": 0.2,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": 4,
            },
        )
        assert monitor.status_code == 201
        detection = client.post(
            f"/v1/detection/monitors/{monitor.json()['id']}/performance",
            json={"as_of": "2026-08-08T12:00:00Z"},
        )
        assert detection.status_code == 200
        assert detection.json()["triggered"] is True
        assert detection.json()["comparison"]["degradation_percent"] == 50.0
        incident_id = detection.json()["incident_id"]

        recovery = client.post(
            f"/v1/incidents/{incident_id}/recovery",
            json={
                "status": "verified",
                "verified_at": "2026-08-08T12:05:00Z",
                "checks": [
                    {
                        "name": "candidate_traffic_removed",
                        "passed": True,
                        "details": {"candidate_traffic_percentage": 0},
                    }
                ],
            },
        )
        assert recovery.status_code == 200
        resolved = client.patch(f"/v1/incidents/{incident_id}", json={"status": "resolved"})
        assert resolved.status_code == 200
        incident = client.get(f"/v1/incidents/{incident_id}").json()
        assert incident["status"] == "resolved"
        assert [event["event_type"] for event in incident["timeline"]] == [
            "created",
            "recovery_verified",
            "status_changed",
        ]


class FakeWorkerDataHub:
    async def collect_context(self, model_urn: str, max_hops: int) -> dict[str, Any]:
        assert model_urn == "urn:li:mlModel:fraud-worker"
        assert max_hops == 3
        return {
            "model": {"urn": model_urn, "type": "ML_MODEL", "name": "fraud-worker"},
            "upstream": {"upstreams": {"searchResults": []}},
            "downstream": {"downstreams": {"searchResults": []}},
            "related_entities": [],
            "tool_trace": ["get_entities", "get_lineage:upstream", "get_lineage:downstream"],
        }

    async def save_investigation(
        self, title: str, content: str, related_assets: list[str]
    ) -> dict[str, Any]:
        return {"urn": "urn:li:document:worker-recovery"}


class SuccessfulAdapter(RemediationAdapter):
    async def execute(self, action: dict[str, Any]) -> ExecutionResult:
        return ExecutionResult(
            status="succeeded",
            external_execution_id=f"provider-{action['id']}",
            details={"provider": "integration-fake", "accepted": True},
        )


def test_continuous_worker_runs_detection_approval_execution_and_verified_recovery(
    integration_settings: Settings,
) -> None:
    app = create_app(integration_settings)
    with TestClient(app) as client:
        assert (
            client.put(
                "/v1/models/fraud-worker",
                json={
                    "name": "fraud-worker",
                    "task": "binary_classification",
                    "positive_class": "blocked",
                    "positive_actual": "chargeback",
                    "datahub_urn": "urn:li:mlModel:fraud-worker",
                },
            ).status_code
            == 200
        )
        for version, status_value, traffic in (
            ("v1", "active", 90),
            ("v2", "monitoring", 10),
        ):
            assert (
                client.post(
                    "/v1/events/deployments",
                    json={
                        "deployment": "fraud-worker-production",
                        "model": "fraud-worker",
                        "version": version,
                        "strategy": "canary",
                        "traffic_percentage": traffic,
                        "status": status_value,
                        "occurred_at": "2026-08-09T11:40:00Z",
                    },
                ).status_code
                == 202
            )

        predictions = []
        actuals = []
        labels = ["chargeback", "chargeback", "legitimate", "legitimate"]
        for version, classes in (
            ("v1", ["blocked", "blocked", "allowed", "allowed"]),
            ("v2", ["blocked", "allowed", "allowed", "allowed"]),
        ):
            for index, (predicted_class, actual) in enumerate(zip(classes, labels, strict=True)):
                prediction_id = f"worker-{version}-{index}"
                predictions.append(
                    {
                        "prediction_id": prediction_id,
                        "model": "fraud-worker",
                        "version": version,
                        "deployment": "fraud-worker-production",
                        "observed_at": f"2026-08-09T11:5{index}:00Z",
                        "predicted_class": predicted_class,
                    }
                )
                actuals.append(
                    {
                        "prediction_id": prediction_id,
                        "actual": actual,
                        "observed_at": f"2026-08-09T11:5{index}:30Z",
                    }
                )
        assert (
            client.post("/v1/events/predictions/batch", json={"events": predictions}).status_code
            == 202
        )
        assert client.post("/v1/events/actuals/batch", json={"events": actuals}).status_code == 202
        monitor_response = client.post(
            "/v1/monitors",
            json={
                "model": "fraud-worker",
                "version": "v2",
                "reference_version": "v1",
                "deployment": "fraud-worker-production",
                "signal": "performance",
                "metric": "recall",
                "operator": "decrease",
                "threshold": 0.2,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": 4,
                "check_interval_seconds": 60,
            },
        )
        assert monitor_response.status_code == 201
        monitor_id = monitor_response.json()["id"]
        as_of = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        with app.state.database.connection() as connection:
            connection.execute(
                "UPDATE monitors SET next_evaluation_at = %s WHERE id = %s",
                (as_of, monitor_id),
            )
            connection.commit()

        evaluation = MonitorEvaluationService(
            app.state.monitors,
            app.state.deployments,
            app.state.models,
            app.state.telemetry,
            app.state.incidents,
        )
        monitor_worker = MonitorWorker(
            "integration-monitor",
            app.state.monitors,
            evaluation,
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        assert monitor_worker.run_once(as_of) == 1
        incidents = app.state.incidents.list(limit=10)
        assert len(incidents) == 1
        incident_id = incidents[0]["id"]
        assert incidents[0]["status"] == "open"
        second_window = datetime(2026, 8, 9, 12, 1, tzinfo=UTC)
        assert monitor_worker.run_once(second_window) == 1
        assert len(app.state.incidents.list(limit=10)) == 1
        assert [event["event_type"] for event in app.state.incidents.events(incident_id)] == [
            "created",
            "signal_repeated",
        ]
        with app.state.database.connection() as connection:
            connection.execute(
                "UPDATE incidents SET investigation_next_attempt_at = %s WHERE id = %s",
                (as_of, incident_id),
            )
            connection.commit()

        datahub = FakeWorkerDataHub()
        investigation_worker = InvestigationWorker(
            "integration-investigation",
            app.state.incidents,
            app.state.models,
            datahub,
            app.state.release_context,
            RemediationService(app.state.remediation),
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        assert asyncio.run(investigation_worker.run_once(as_of)) == 1
        actions = app.state.remediation.list_for_incident(incident_id)
        assert len(actions) == 1
        action_id = actions[0]["id"]
        assert actions[0]["action_type"] == "stop_canary"
        assert actions[0]["status"] == "proposed"

        unauthorized = client.post(
            f"/v1/actions/{action_id}/approval", json={"decision": "approve"}
        )
        assert unauthorized.status_code == 401
        approved = client.post(
            f"/v1/actions/{action_id}/approval",
            json={"decision": "approve", "reason": "Canary recall regressed by 50%"},
            headers={"Authorization": "Bearer integration-approver-token"},
        )
        assert approved.status_code == 200
        assert approved.json()["status"] == "approved"

        action_worker = ActionWorker(
            "integration-action",
            app.state.remediation,
            {"webhook": SuccessfulAdapter()},
            batch_size=10,
            lease_seconds=60,
        )
        execution_at = datetime(2026, 8, 9, 12, 1, tzinfo=UTC)
        assert asyncio.run(action_worker.run_once(execution_at)) == 1
        assert app.state.remediation.get(action_id)["status"] == "succeeded"

        assert (
            client.post(
                "/v1/events/deployments",
                json={
                    "deployment": "fraud-worker-production",
                    "model": "fraud-worker",
                    "version": "v2",
                    "strategy": "canary",
                    "traffic_percentage": 0,
                    "status": "rolled_back",
                    "occurred_at": "2026-08-09T12:02:00Z",
                },
            ).status_code
            == 202
        )
        recovery_predictions = []
        recovery_actuals = []
        for index, (predicted_class, actual) in enumerate(
            zip(
                ["blocked", "blocked", "allowed", "allowed"],
                labels,
                strict=True,
            )
        ):
            prediction_id = f"worker-recovery-v1-{index}"
            recovery_predictions.append(
                {
                    "prediction_id": prediction_id,
                    "model": "fraud-worker",
                    "version": "v1",
                    "deployment": "fraud-worker-production",
                    "observed_at": f"2026-08-09T12:03:0{index}Z",
                    "predicted_class": predicted_class,
                }
            )
            recovery_actuals.append(
                {
                    "prediction_id": prediction_id,
                    "actual": actual,
                    "observed_at": f"2026-08-09T12:03:1{index}Z",
                }
            )
        assert (
            client.post(
                "/v1/events/predictions/batch", json={"events": recovery_predictions}
            ).status_code
            == 202
        )
        assert (
            client.post("/v1/events/actuals/batch", json={"events": recovery_actuals}).status_code
            == 202
        )
        recovery_worker = RecoveryWorker(
            "integration-recovery",
            app.state.remediation,
            app.state.incidents,
            app.state.models,
            datahub,
            app.state.release_context,
            RecoveryEvaluator(app.state.deployments, app.state.changes, evaluation),
            write_back=False,
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        recovery_at = datetime(2026, 8, 9, 12, 5, tzinfo=UTC)
        assert asyncio.run(recovery_worker.run_once(recovery_at)) == 1

        incident = client.get(f"/v1/incidents/{incident_id}").json()
        action = client.get(f"/v1/actions/{action_id}").json()
        assert incident["status"] == "resolved"
        assert incident["evidence"]["root_cause_status"] == "confirmed_cause"
        assert action["recovery_verified_at"] == "2026-08-09T12:05:00Z"
        assert action["approval"]["actor_id"] == "risk-lead@example.com"
        assert [check["name"] for check in incident["evidence"]["recovery"]["checks"]] == [
            "approved_action_execution_succeeded",
            "released_version_traffic_removed",
            "fresh_performance_window_passed",
        ]
        assert [event["event_type"] for event in action["timeline"]] == [
            "proposed",
            "approved",
            "execution_started",
            "execution_succeeded",
            "recovery_verified",
        ]
        with app.state.database.connection() as connection:
            runs = connection.execute(
                "SELECT * FROM monitor_runs WHERE monitor_id = %s", (monitor_id,)
            ).fetchall()
        assert len(runs) == 2
        assert all(run["status"] == "evaluated" for run in runs)
        assert all(run["triggered"] is True for run in runs)


GITOPS_MANIFEST = """\
apiVersion: histograph.ai/v1
kind: ModelDeployment
metadata:
  name: fraud-gitops-production
spec:
  environment: production
  model:
    name: fraud-gitops
    task: binary_classification
    positiveClass: blocked
    positiveActual: chargeback
    datahubModelUrn: urn:li:mlModel:fraud-gitops
  runtime:
    provider: reference
    endpoint: https://fraud.example.com
  stable:
    version: v1
    artifact: artifact.joblib
    trafficPercentage: 90
    configuration:
      decisionThreshold: 0.5
  candidate:
    version: v2
    artifact: artifact.joblib
    trafficPercentage: 10
    configuration:
      decisionThreshold: 0.95
"""


class IntegrationProbabilityModel:
    def predict_proba(self, frame):
        probabilities = [float(value) for value in frame["amount"]]
        return [[1 - probability, probability] for probability in probabilities]


class IntegrationTelemetrySink:
    def __init__(self, client: TestClient):
        self._client = client

    async def send(self, event_type: str, payload: dict[str, Any]) -> None:
        paths = {
            "predictions": "/v1/events/predictions/batch",
            "actuals": "/v1/events/actuals/batch",
            "deployment": "/v1/events/deployments",
            "change": "/v1/events/changes",
        }
        response = self._client.post(paths[event_type], json=payload)
        assert response.status_code == 202


class IntegrationGitHubClient:
    def __init__(self) -> None:
        self.content = GITOPS_MANIFEST
        self.revision = "release-sha"
        self.proposed_content: str | None = None

    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        assert connection["repository_owner"] == "example"
        return GitHubRepositoryFile(
            content=self.content,
            blob_sha=f"blob-{self.revision}",
            revision=self.revision,
        )

    async def create_pull_request(
        self,
        connection: dict[str, Any],
        *,
        head_branch: str,
        content: str,
        title: str,
        body: str,
    ) -> CreatedPullRequest:
        assert connection["manifest_path"] == "deployments/fraud.yaml"
        assert title.startswith("fix: roll back fraud-gitops-production")
        assert "authorized remediation decision" in body
        self.proposed_content = content
        return CreatedPullRequest(
            number=42,
            url="https://github.com/example/deployments/pull/42",
            head_branch=head_branch,
        )


class ContractGitHubClient:
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parents[3]

    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        return await self.get_repository_file(connection, str(connection["manifest_path"]))

    async def get_repository_file(
        self,
        connection: dict[str, Any],
        path: str,
        *,
        revision: str | None = None,
    ) -> GitHubRepositoryFile:
        assert revision in {None, "contract-sha"}
        content = (self.root / path).read_text()
        if path == ".histograph/deployments/mobile-money-fraud.yaml":
            content = yaml.safe_dump(_active_contract_manifest(self.root), sort_keys=False)
        return GitHubRepositoryFile(
            content=content,
            blob_sha=f"blob-{path}",
            revision=revision or "contract-sha",
        )

    async def create_pull_request(
        self,
        connection: dict[str, Any],
        *,
        head_branch: str,
        content: str,
        title: str,
        body: str,
    ) -> CreatedPullRequest:
        return CreatedPullRequest(
            number=99, url="https://example.test/pull/99", head_branch=head_branch
        )


class ContractRuntimeConnector(RuntimeConnector):
    def __init__(self) -> None:
        self.root = Path(__file__).resolve().parents[3]

    async def state(self, deployment: dict[str, Any]) -> dict[str, Any]:
        assert deployment["deployment"] == "mobile-money-fraud-production"
        return {
            "status": "ready",
            "revision": "contract-sha",
            "manifest": _active_contract_manifest(self.root),
            "applied_at": "2026-08-10T11:10:20Z",
            "outbox_pending": 0,
        }


def _active_contract_manifest(root: Path) -> dict[str, Any]:
    manifest = yaml.safe_load(
        (root / ".histograph/deployments/mobile-money-fraud.yaml").read_text()
    )
    manifest["spec"]["stable"]["trafficPercentage"] = 90
    manifest["spec"]["candidate"]["trafficPercentage"] = 10
    return manifest


def test_client_read_models_and_durable_demo_queue_use_the_imported_contract(
    integration_settings: Settings,
) -> None:
    settings = integration_settings.model_copy(
        update={
            "demo_control_token": "demo-control",
            "reference_control_token": "runtime-control",
            "demo_runtime_url": "http://runtime:8100",
        }
    )
    app = create_app(
        settings,
        github_client=ContractGitHubClient(),
        runtime_connector=ContractRuntimeConnector(),
    )
    configuration = {"Authorization": "Bearer integration-github-config-token"}
    with TestClient(app) as client:
        connected = client.post(
            "/v1/integrations/github/connections",
            headers=configuration,
            json={
                "installation_id": 123,
                "repository_owner": "example",
                "repository_name": "deployments",
                "branch": "main",
                "manifest_path": ".histograph/deployments/mobile-money-fraud.yaml",
            },
        )
        connection_id = connected.json()["id"]
        imported = client.post(
            f"/v1/integrations/github/connections/{connection_id}/sync",
            headers=configuration,
        )
        assert imported.status_code == 200
        deployment = client.get("/v1/deployments").json()[0]
        assert deployment["sync_status"] == "in_sync"
        assert set(deployment["observed_state"]["model_versions"]) == {"v1", "v2"}
        assert deployment["input_schema"]["title"] == "Mobile money fraud prediction"
        assert len(deployment["examples"]) == 2
        assert "manifest_content" not in deployment

        started = client.post(
            "/v1/demo/scenarios",
            headers={"Authorization": "Bearer demo-control"},
            json={"deployment_id": deployment["id"]},
        )
        assert started.status_code == 202
        assert started.json()["stage"] == "queued"
        assert "baseline_manifest" not in started.json()["result"]
        run_id = started.json()["id"]
        duplicate = client.post(
            "/v1/demo/scenarios",
            headers={"Authorization": "Bearer demo-control"},
            json={"deployment_id": deployment["id"]},
        )
        assert duplicate.status_code == 409
        overview = client.get("/v1/overview").json()
        assert overview["counts"]["deployments"] == 1
        assert overview["latest_demo_run"]["stage"] == "queued"
        assert app.state.rate_limits.consume(
            "integration-playground", "test-client", limit=2, window_seconds=60
        )
        assert app.state.rate_limits.consume(
            "integration-playground", "test-client", limit=2, window_seconds=60
        )
        assert not app.state.rate_limits.consume(
            "integration-playground", "test-client", limit=2, window_seconds=60
        )
        with app.state.database.connection() as database_connection:
            database_connection.execute(
                """
                UPDATE demo_runs
                SET status = 'running', stage = 'verifying'
                WHERE id = %s
                """,
                (run_id,),
            )
            database_connection.commit()
        claimed_recovery = app.state.demo_runs.claim_recovery_ready(
            "integration-demo-worker",
            datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
            10,
            60,
        )
        assert [str(item["id"]) for item in claimed_recovery] == [run_id]
        assert (
            app.state.demo_runs.claim_recovery_ready(
                "another-worker",
                datetime(2026, 8, 10, 12, 0, tzinfo=UTC),
                10,
                60,
            )
            == []
        )
        app.state.demo_runs.mark_recovery_emitted(
            UUID(run_id),
            {"status": "fresh_recovery_evidence_emitted", "routing_counts": {"v1": 1000}},
        )
        persisted_run = app.state.demo_runs.get(UUID(run_id))
        assert persisted_run is not None
        assert persisted_run["result"]["recovery_traffic"]["routing_counts"] == {"v1": 1000}
        with app.state.database.connection() as database_connection:
            database_connection.execute(
                """
                UPDATE demo_runs
                SET status = 'resolved', stage = 'resolved', finished_at = NOW()
                WHERE id = %s
                """,
                (run_id,),
            )
            database_connection.commit()
        reset = client.post(
            f"/v1/demo/scenarios/{run_id}/reset",
            headers={"Authorization": "Bearer demo-control"},
        )
        assert reset.status_code == 202
        assert reset.json()["pull_request_number"] == 99
        repeated_reset = client.post(
            f"/v1/demo/scenarios/{run_id}/reset",
            headers={"Authorization": "Bearer demo-control"},
        )
        assert repeated_reset.json() == reset.json()


class GitOpsWorkerDataHub:
    async def collect_context(self, model_urn: str, max_hops: int) -> dict[str, Any]:
        assert model_urn == "urn:li:mlModel:fraud-gitops"
        assert max_hops == 3
        return {
            "model": {"urn": model_urn, "type": "ML_MODEL", "name": "fraud-gitops"},
            "upstream": {"upstreams": {"searchResults": []}},
            "downstream": {"downstreams": {"searchResults": []}},
            "related_entities": [],
            "tool_trace": ["get_entities", "get_lineage:upstream", "get_lineage:downstream"],
        }

    async def save_investigation(
        self, title: str, content: str, related_assets: list[str]
    ) -> dict[str, Any]:
        return {"urn": "urn:li:document:gitops-recovery"}


def _github_webhook_headers(event: str, delivery: str, body: bytes) -> dict[str, str]:
    signature = hmac.new(b"integration-github-webhook-secret", body, hashlib.sha256).hexdigest()
    return {
        "Content-Type": "application/json",
        "X-GitHub-Event": event,
        "X-GitHub-Delivery": delivery,
        "X-Hub-Signature-256": f"sha256={signature}",
    }


def test_gitops_pr_merge_drives_execution_and_independently_verified_recovery(
    integration_settings: Settings,
    tmp_path: Path,
) -> None:
    joblib.dump(
        {
            "model": IntegrationProbabilityModel(),
            "threshold": 0.5,
            "features": ["amount"],
        },
        tmp_path / "artifact.joblib",
    )
    github_client = IntegrationGitHubClient()
    app = create_app(integration_settings, github_client=github_client)
    configuration_headers = {"Authorization": "Bearer integration-github-config-token"}
    with TestClient(app) as client:
        unauthorized = client.post(
            "/v1/integrations/github/connections",
            json={
                "installation_id": 123,
                "repository_owner": "example",
                "repository_name": "deployments",
                "branch": "main",
                "manifest_path": "deployments/fraud.yaml",
            },
        )
        assert unauthorized.status_code == 401
        connection = client.post(
            "/v1/integrations/github/connections",
            json={
                "installation_id": 123,
                "repository_owner": "example",
                "repository_name": "deployments",
                "branch": "main",
                "manifest_path": "deployments/fraud.yaml",
            },
            headers=configuration_headers,
        )
        assert connection.status_code == 201
        connection_id = connection.json()["id"]
        imported = client.post(
            f"/v1/integrations/github/connections/{connection_id}/sync",
            headers=configuration_headers,
        )
        assert imported.status_code == 200
        assert imported.json()["sync_status"] == "desired_only"
        assert client.get("/v1/models/fraud-gitops").status_code == 200
        demo_run_id = app.state.demo_runs.start(imported.json(), "integration-demo")

        runtime_state = RuntimeStateStore(tmp_path / "runtime.sqlite3")
        reference_runtime = ReferenceRuntime(tmp_path, runtime_state)
        telemetry_worker = TelemetryWorker(
            runtime_state,
            IntegrationTelemetrySink(client),
            batch_size=20,
            retry_seconds=5,
        )
        reference_runtime.apply(
            "release-sha",
            github_client.content,
            datetime(2026, 8, 9, 11, 40, tzinfo=UTC),
        )
        assert asyncio.run(telemetry_worker.run_once(datetime(2030, 8, 9, tzinfo=UTC))) == 2
        deployments = client.get(
            "/v1/integrations/github/deployments", headers=configuration_headers
        ).json()
        assert deployments[0]["sync_status"] == "in_sync"

        prediction_requests = [
            PredictionRequest(
                prediction_id=f"gitops-runtime-{index}",
                features={"amount": 0.9 if index % 2 == 0 else 0.1},
                observed_at=datetime(2026, 8, 9, 11, 55, tzinfo=UTC),
            )
            for index in range(500)
        ]
        predictions = reference_runtime.predict_many(prediction_requests)
        assert 35 <= sum(prediction.version == "v2" for prediction in predictions) <= 65
        reference_runtime.record_outcomes(
            [
                OutcomeRequest(
                    prediction_id=prediction.prediction_id,
                    actual="chargeback" if index % 2 == 0 else "legitimate",
                    observed_at=datetime(2026, 8, 9, 11, 56, tzinfo=UTC),
                )
                for index, prediction in enumerate(predictions)
            ]
        )
        assert asyncio.run(telemetry_worker.run_once(datetime(2030, 8, 9, tzinfo=UTC))) == 2
        monitor = client.post(
            "/v1/monitors",
            json={
                "model": "fraud-gitops",
                "version": "v2",
                "reference_version": "v1",
                "deployment": "fraud-gitops-production",
                "signal": "performance",
                "metric": "recall",
                "operator": "decrease",
                "threshold": 0.2,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": 20,
                "check_interval_seconds": 60,
            },
        )
        assert monitor.status_code == 201
        monitor_id = monitor.json()["id"]
        app.state.demo_runs.mark_emitted(
            demo_run_id,
            UUID(monitor_id),
            {"monitor_id": monitor_id, "status": "awaiting_continuous_worker"},
        )
        as_of = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
        with app.state.database.connection() as database_connection:
            database_connection.execute(
                "UPDATE monitors SET next_evaluation_at = %s WHERE id = %s",
                (as_of, monitor_id),
            )
            database_connection.commit()
        evaluation = MonitorEvaluationService(
            app.state.monitors,
            app.state.deployments,
            app.state.models,
            app.state.telemetry,
            app.state.incidents,
        )
        monitor_worker = MonitorWorker(
            "gitops-monitor",
            app.state.monitors,
            evaluation,
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        assert monitor_worker.run_once(as_of) == 1
        incident_id = app.state.incidents.list(limit=10)[0]["id"]
        with app.state.database.connection() as database_connection:
            database_connection.execute(
                "UPDATE incidents SET investigation_next_attempt_at = %s WHERE id = %s",
                (as_of, incident_id),
            )
            database_connection.commit()
        datahub = GitOpsWorkerDataHub()
        investigation_worker = InvestigationWorker(
            "gitops-investigation",
            app.state.incidents,
            app.state.models,
            datahub,
            app.state.release_context,
            RemediationService(app.state.remediation, app.state.gitops),
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        assert asyncio.run(investigation_worker.run_once(as_of)) == 1
        action = app.state.remediation.list_for_incident(incident_id)[0]
        action_id = action["id"]
        assert action["adapter"] == "github_pr"
        proposal_worker = GitOpsProposalWorker(
            "gitops-proposal",
            app.state.gitops,
            github_client,
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        assert asyncio.run(proposal_worker.run_once(as_of)) == 1
        proposed = client.get(f"/v1/actions/{action_id}").json()
        assert proposed["status"] == "proposed"
        assert proposed["approval"] is None
        assert proposed["pull_request"]["pull_request_number"] == 42
        tracked_run = app.state.demo_runs.refresh(demo_run_id)
        assert tracked_run is not None
        assert tracked_run["stage"] == "awaiting_approval"
        assert tracked_run["incident_id"] == incident_id
        assert tracked_run["action_id"] == action_id

        merge_payload = {
            "action": "closed",
            "repository": {"name": "deployments", "owner": {"login": "example"}},
            "sender": {"login": "risk-lead"},
            "pull_request": {
                "number": 42,
                "merged": True,
                "merge_commit_sha": "merge-sha",
                "merged_at": "2026-08-09T12:01:00Z",
                "merged_by": {"login": "risk-lead"},
            },
        }
        merge_body = json.dumps(merge_payload, separators=(",", ":")).encode()
        merged = client.post(
            "/v1/integrations/github/webhook",
            content=merge_body,
            headers=_github_webhook_headers("pull_request", "delivery-merge", merge_body),
        )
        assert merged.status_code == 202
        assert merged.json()["status"] == "executing"
        duplicate_merge = client.post(
            "/v1/integrations/github/webhook",
            content=merge_body,
            headers=_github_webhook_headers("pull_request", "delivery-merge", merge_body),
        )
        assert duplicate_merge.status_code == 202
        assert duplicate_merge.json()["status"] == "duplicate"
        executing = client.get(f"/v1/actions/{action_id}").json()
        assert executing["approval"]["actor_id"] == "github:risk-lead"
        assert executing["status"] == "executing"

        assert github_client.proposed_content is not None
        github_client.content = github_client.proposed_content
        github_client.revision = "merge-sha"
        push_payload = {
            "ref": "refs/heads/main",
            "repository": {"name": "deployments", "owner": {"login": "example"}},
        }
        push_body = json.dumps(push_payload, separators=(",", ":")).encode()
        pushed = client.post(
            "/v1/integrations/github/webhook",
            content=push_body,
            headers=_github_webhook_headers("push", "delivery-push", push_body),
        )
        assert pushed.status_code == 202
        assert pushed.json()["status"] == "synced"

        reference_runtime.apply(
            "merge-sha",
            github_client.content,
            datetime(2026, 8, 9, 12, 2, tzinfo=UTC),
        )
        assert asyncio.run(telemetry_worker.run_once(datetime(2030, 8, 9, tzinfo=UTC))) == 2
        deployment_payload = {
            "repository": {"name": "deployments", "owner": {"login": "example"}},
            "deployment": {"id": 91, "sha": "merge-sha", "environment": "production"},
            "deployment_status": {
                "state": "success",
                "log_url": "https://ci/run/91",
                "created_at": "2026-08-09T12:03:00Z",
            },
        }
        deployment_body = json.dumps(deployment_payload, separators=(",", ":")).encode()
        deployed = client.post(
            "/v1/integrations/github/webhook",
            content=deployment_body,
            headers=_github_webhook_headers(
                "deployment_status", "delivery-deployment", deployment_body
            ),
        )
        assert deployed.status_code == 202
        assert deployed.json()["status"] == "succeeded"

        recovery_prediction_requests = [
            PredictionRequest(
                prediction_id=f"gitops-recovery-{index}",
                features={"amount": 0.9 if index % 2 == 0 else 0.1},
                observed_at=datetime(2026, 8, 9, 12, 3, 30, tzinfo=UTC),
            )
            for index in range(40)
        ]
        recovery_predictions = reference_runtime.predict_many(recovery_prediction_requests)
        assert {prediction.version for prediction in recovery_predictions} == {"v1"}
        reference_runtime.record_outcomes(
            [
                OutcomeRequest(
                    prediction_id=prediction.prediction_id,
                    actual="chargeback" if index % 2 == 0 else "legitimate",
                    observed_at=datetime(2026, 8, 9, 12, 4, tzinfo=UTC),
                )
                for index, prediction in enumerate(recovery_predictions)
            ]
        )
        assert asyncio.run(telemetry_worker.run_once(datetime(2030, 8, 9, tzinfo=UTC))) == 2

        recovery_worker = RecoveryWorker(
            "gitops-recovery",
            app.state.remediation,
            app.state.incidents,
            app.state.models,
            datahub,
            app.state.release_context,
            RecoveryEvaluator(app.state.deployments, app.state.changes, evaluation),
            write_back=False,
            batch_size=10,
            lease_seconds=60,
            retry_seconds=30,
        )
        recovery_at = datetime(2026, 8, 9, 12, 5, tzinfo=UTC)
        assert asyncio.run(recovery_worker.run_once(recovery_at)) == 1

        final_action = client.get(f"/v1/actions/{action_id}").json()
        final_incident = client.get(f"/v1/incidents/{incident_id}").json()
        final_deployment = client.get(
            "/v1/integrations/github/deployments", headers=configuration_headers
        ).json()[0]
        assert final_action["status"] == "succeeded"
        assert final_action["recovery_verified_at"] == "2026-08-09T12:05:00Z", (
            final_action["last_error"],
            final_action["target"],
            final_action["execution_started_at"],
            final_action["execution_finished_at"],
        )
        assert final_incident["status"] == "resolved"
        assert final_incident["evidence"]["root_cause_status"] == "confirmed_cause"
        assert [check["name"] for check in final_incident["evidence"]["recovery"]["checks"]] == [
            "approved_action_execution_succeeded",
            "released_version_traffic_removed",
            "fresh_performance_window_passed",
        ]
        assert final_deployment["desired_revision"] == "merge-sha"
        assert final_deployment["sync_status"] == "in_sync"
        completed_run = app.state.demo_runs.refresh(demo_run_id)
        assert completed_run is not None
        assert completed_run["status"] == "resolved"
        assert completed_run["stage"] == "resolved"
        assert [event["event_type"] for event in final_action["timeline"]] == [
            "proposed",
            "approved",
            "execution_started",
            "execution_accepted",
            "execution_succeeded",
            "recovery_verified",
        ]
