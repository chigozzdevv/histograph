import asyncio
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import joblib
import pytest
from demo.runtime.app import create_runtime_app
from demo.runtime.reconciler import ReferenceDeploymentReconciler
from demo.runtime.settings import ReferenceRuntimeSettings
from demo.runtime.state import RuntimeStateStore
from fastapi.testclient import TestClient

from histograph.integrations.github.manifest import parse_manifest, render_rollback
from histograph.integrations.github.types import (
    CreatedDeployment,
    CreatedPullRequest,
    GitHubRepositoryFile,
)


class AmountProbabilityModel:
    def predict_proba(self, frame):
        probabilities = [min(max(float(value) / 100, 0.01), 0.9) for value in frame["amount"]]
        return [[1 - probability, probability] for probability in probabilities]


class RecordingSink:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, Any]]] = []

    async def send(self, event_type: str, payload: dict[str, Any]) -> None:
        self.events.append((event_type, payload))


def _manifest(artifact: str, *, feature_version: str = "v1", scale: int = 1) -> str:
    rollback = ""
    if feature_version == "v2":
        rollback = """\
      rollbackVersion: v1
      rollbackConfiguration:
        scaleMultiplier: 1
"""
    return f"""\
apiVersion: histograph.ai/v1
kind: ModelDeployment
metadata:
  name: fraud-production
spec:
  environment: production
  model:
    name: fraud
    task: binary_classification
    positiveClass: fraud
    positiveActual: 1
    datahubModelUrn: urn:li:mlModel:fraud
  runtime:
    provider: reference
    endpoint: http://runtime:8100
  stable:
    version: v1
    artifact: {artifact}
    trafficPercentage: 90
    configuration:
      decisionThreshold: 0.5
  candidate:
    version: v2
    artifact: {artifact}
    trafficPercentage: 10
    configuration:
      decisionThreshold: 0.99
  features:
    - name: transaction-amount
      assetUrn: urn:li:mlFeature:(fraud,amount)
      inputFeature: amount
      version: {feature_version}
      configuration:
        scaleMultiplier: {scale}
{rollback}"""


def _artifact(workspace: Path) -> str:
    path = workspace / "artifact.joblib"
    joblib.dump(
        {
            "model": AmountProbabilityModel(),
            "threshold": 0.5,
            "features": ["amount", "transaction_type"],
        },
        path,
    )
    return path.name


def test_reference_runtime_serves_canary_and_emits_durable_observed_evidence(
    tmp_path: Path,
) -> None:
    artifact = _artifact(tmp_path)
    settings = ReferenceRuntimeSettings(
        workspace_root=tmp_path,
        state_path=tmp_path / "runtime.sqlite3",
        control_token="runtime-secret",
        telemetry_poll_seconds=60,
    )
    sink = RecordingSink()
    app = create_runtime_app(settings, telemetry_sink=sink)
    content = _manifest(artifact)
    events = [
        {
            "prediction_id": f"prediction-{index}",
            "features": {"amount": 90, "transaction_type": "TRANSFER"},
            "observed_at": "2026-08-09T12:00:00Z",
        }
        for index in range(1000)
    ]

    with TestClient(app) as client:
        assert (
            client.post(
                "/v1/deployments/apply", json={"revision": "sha-1", "content": content}
            ).status_code
            == 401
        )
        applied = client.post(
            "/v1/deployments/apply",
            json={"revision": "sha-1", "content": content},
            headers={"Authorization": "Bearer runtime-secret"},
        )
        assert applied.status_code == 200
        pending_before_compare = client.get("/v1/runtime").json()["outbox_pending"]

        compared = client.post(
            "/v1/compare",
            json=events[0],
            headers={"Authorization": "Bearer runtime-secret"},
        )
        assert compared.status_code == 200
        assert compared.json()["stable"]["version"] == "v1"
        assert compared.json()["candidate"]["version"] == "v2"
        assert client.get("/v1/runtime").json()["outbox_pending"] == pending_before_compare

        first = client.post("/v1/predict/batch", json={"events": events})
        second = client.post("/v1/predict/batch", json={"events": events})
        assert first.status_code == second.status_code == 200
        first_events = first.json()["events"]
        second_events = second.json()["events"]
        versions = [event["version"] for event in first_events]
        assert versions == [event["version"] for event in second_events]
        assert 80 <= versions.count("v2") <= 120
        assert all(
            event["predicted_class"] == ("fraud" if event["version"] == "v1" else "not_fraud")
            for event in first_events
        )
        assert client.get("/v1/runtime").json()["outbox_pending"] == 5

        rollback = render_rollback(
            content,
            {
                "action_type": "stop_canary",
                "target": {
                    "deployment": "fraud-production",
                    "model": "fraud",
                    "version": "v2",
                    "environment": "production",
                },
            },
        )
        assert (
            client.post(
                "/v1/deployments/apply",
                json={"revision": "sha-2", "content": rollback},
                headers={"Authorization": "Bearer runtime-secret"},
            ).status_code
            == 200
        )
        recovered = client.post("/v1/predict/batch", json={"events": events[:100]})
        assert {event["version"] for event in recovered.json()["events"]} == {"v1"}

        flushed = app.state.telemetry_worker.run_once(datetime(2030, 8, 9, 13, tzinfo=UTC))
        assert asyncio.run(flushed) == 9
        assert client.get("/v1/runtime").json()["outbox_pending"] == 0

    deployment_events = [payload for kind, payload in sink.events if kind == "deployment"]
    assert any(
        event["version"] == "v2"
        and event["traffic_percentage"] == 0
        and event["status"] == "stopped"
        for event in deployment_events
    )


def test_reference_runtime_applies_declared_feature_rollback(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    state = RuntimeStateStore(tmp_path / "feature-runtime.sqlite3")
    from demo.runtime.service import ReferenceRuntime
    from demo.runtime.types import PredictionRequest

    runtime = ReferenceRuntime(tmp_path, state)
    released = _manifest(artifact, feature_version="v2", scale=100)
    runtime.apply("feature-v2", released, datetime(2026, 8, 9, 12, tzinfo=UTC))
    before = runtime.predict(
        PredictionRequest(
            prediction_id="stable-route",
            features={"amount": 0.9, "transaction_type": "TRANSFER"},
        )
    )
    rolled_back = render_rollback(
        released,
        {
            "action_type": "rollback_release",
            "target": {
                "deployment": "fraud-production",
                "model": "fraud",
                "version": "v2",
                "environment": "production",
                "asset_urn": "urn:li:mlFeature:(fraud,amount)",
            },
        },
    )
    runtime.apply("feature-v1", rolled_back, datetime(2026, 8, 9, 12, 1, tzinfo=UTC))
    after = runtime.predict(
        PredictionRequest(
            prediction_id="stable-route",
            features={"amount": 0.9, "transaction_type": "TRANSFER"},
        )
    )

    assert parse_manifest(rolled_back).spec.features[0].configuration == {"scaleMultiplier": 1}
    assert before.score == pytest.approx(0.9)
    assert after.score == pytest.approx(0.01)


class FakeDeploymentGitHub:
    def __init__(self, content: str):
        self.content = content
        self.statuses: list[str] = []
        self.created = 0

    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        return GitHubRepositoryFile(content=self.content, blob_sha="blob", revision="merge-sha")

    async def create_pull_request(self, *args, **kwargs) -> CreatedPullRequest:
        raise AssertionError("Reconciler must not create pull requests")

    async def create_deployment(self, *args, **kwargs) -> CreatedDeployment:
        self.created += 1
        return CreatedDeployment(id=71, revision="merge-sha")

    async def create_deployment_status(self, *args, state: str, **kwargs) -> None:
        self.statuses.append(state)


class FakeRuntimeControl:
    def __init__(self):
        self.revision: str | None = None
        self.applied = 0

    async def state(self) -> dict[str, Any]:
        return {"revision": self.revision}

    async def apply(self, revision: str, content: str) -> dict[str, Any]:
        self.revision = revision
        self.applied += 1
        return {"status": "applied"}


@pytest.mark.asyncio
async def test_reference_reconciler_reports_real_apply_status_once(tmp_path: Path) -> None:
    artifact = _artifact(tmp_path)
    github = FakeDeploymentGitHub(_manifest(artifact))
    runtime = FakeRuntimeControl()
    state = RuntimeStateStore(tmp_path / "reconciler.sqlite3")
    reconciler = ReferenceDeploymentReconciler(
        {
            "installation_id": 1,
            "repository_owner": "example",
            "repository_name": "deployments",
            "branch": "main",
            "manifest_path": "deployment.yaml",
        },
        github,
        runtime,
        state,
    )

    assert (await reconciler.run_once())["status"] == "applied"
    assert (await reconciler.run_once())["status"] == "unchanged"
    assert github.created == 1
    assert github.statuses == ["in_progress", "success"]
    assert runtime.applied == 1
