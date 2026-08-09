import base64
import hashlib
import hmac
import json
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from histograph.integrations.github.auth import verify_webhook_signature
from histograph.integrations.github.client import GitHubAppClient
from histograph.integrations.github.manifest import (
    UnsafeRollback,
    parse_manifest,
    render_rollback,
)
from histograph.integrations.github.service import GitHubWebhookService
from histograph.integrations.github.types import CreatedPullRequest, GitHubRepositoryFile
from histograph.integrations.github.workers import GitOpsProposalWorker
from histograph.models.types import ModelDefinition

VALID_MANIFEST = """\
apiVersion: histograph.ai/v1
kind: ModelDeployment
metadata:
  name: fraud-production
spec:
  environment: production
  model:
    name: fraud
    task: binary_classification
    positiveClass: blocked
    positiveActual: chargeback
    datahubModelUrn: urn:li:mlModel:fraud
  runtime:
    provider: reference
    endpoint: https://fraud.example.com
  stable:
    version: v1
    artifact: ghcr.io/example/fraud:v1
    trafficPercentage: 90
  candidate:
    version: v2
    artifact: ghcr.io/example/fraud:v2
    trafficPercentage: 10
  features:
    - name: transaction-amount
      assetUrn: urn:li:mlFeature:(fraud,amount)
      inputFeature: amount
      version: v2
      configuration:
        scaleMultiplier: 100
      rollbackVersion: v1
      rollbackConfiguration:
        scaleMultiplier: 1
"""


def _action(action_type: str = "stop_canary") -> dict[str, Any]:
    return {
        "id": uuid4(),
        "incident_id": uuid4(),
        "action_type": action_type,
        "target": {
            "model": "fraud",
            "version": "v2",
            "deployment": "fraud-production",
            "environment": "production",
            "asset_urn": "urn:li:mlFeature:(fraud,amount)",
        },
        "evidence": {"investigation_status": "probable_cause"},
        "manifest_content": VALID_MANIFEST,
        "manifest_sha": "blob-sha",
        "head_branch": "histograph/rollback-test",
        "installation_id": 123,
        "repository_owner": "example",
        "repository_name": "deployments",
        "branch": "main",
        "manifest_path": "deployments/fraud.yaml",
    }


def test_manifest_declares_model_identity_and_renders_bounded_canary_stop() -> None:
    manifest = parse_manifest(VALID_MANIFEST)

    rendered = render_rollback(VALID_MANIFEST, _action())
    rollback = parse_manifest(rendered)

    assert manifest.spec.model.datahub_urn == "urn:li:mlModel:fraud"
    assert rollback.spec.stable.traffic_percentage == 100
    assert rollback.spec.candidate is not None
    assert rollback.spec.candidate.version == "v2"
    assert rollback.spec.candidate.traffic_percentage == 0


def test_manifest_rollback_abstains_on_target_mismatch_or_missing_explicit_target() -> None:
    wrong_target = _action()
    wrong_target["target"] = {**wrong_target["target"], "deployment": "another-deployment"}

    with pytest.raises(UnsafeRollback, match="does not match"):
        render_rollback(VALID_MANIFEST, wrong_target)
    model_rollback = _action("rollback_model")
    model_rollback["target"] = {**model_rollback["target"], "version": "v1"}
    with pytest.raises(UnsafeRollback, match="explicit model rollback target"):
        render_rollback(VALID_MANIFEST, model_rollback)


def test_feature_rollback_uses_only_the_manifest_declared_previous_version() -> None:
    rendered = render_rollback(VALID_MANIFEST, _action("rollback_release"))
    rollback = parse_manifest(rendered)

    assert rollback.spec.features[0].version == "v1"
    assert rollback.spec.features[0].configuration == {"scaleMultiplier": 1}
    assert rollback.spec.features[0].rollback_version is None


def test_webhook_signature_is_required_and_compared_over_the_raw_body() -> None:
    body = b'{"action":"closed"}'
    signature = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()

    verify_webhook_signature(body, signature, "secret")

    with pytest.raises(PermissionError, match="invalid"):
        verify_webhook_signature(body + b" ", signature, "secret")


class FakeProposalRepository:
    def __init__(self, action: dict[str, Any]):
        self.action = action
        self.completed: tuple[UUID, CreatedPullRequest] | None = None
        self.failed: tuple[UUID, str] | None = None
        self.cancelled: tuple[UUID, str] | None = None

    def claim_pull_request_proposals(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]:
        assert worker_id == "gitops-worker"
        assert (limit, lease_seconds) == (10, 60)
        return [self.action]

    def complete_pull_request(self, action_id: UUID, result: CreatedPullRequest) -> None:
        self.completed = (action_id, result)

    def fail_pull_request(
        self,
        action_id: UUID,
        error: str,
        failed_at: datetime,
        retry_seconds: int,
    ) -> None:
        self.failed = (action_id, error)

    def cancel_stale_proposal(self, action_id: UUID, reason: str) -> None:
        self.cancelled = (action_id, reason)


class FakeGitHubClient:
    def __init__(self) -> None:
        self.content: str | None = None

    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        return GitHubRepositoryFile(
            content=VALID_MANIFEST,
            blob_sha="blob-sha",
            revision="commit-sha",
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
        assert connection["repository_name"] == "deployments"
        assert title.startswith("fix: roll back fraud-production")
        assert "Merging this pull request is the authorized remediation decision" in body
        self.content = content
        return CreatedPullRequest(
            number=42,
            url="https://github.com/example/deployments/pull/42",
            head_branch=head_branch,
        )


@pytest.mark.asyncio
async def test_proposal_worker_opens_a_reviewable_pr_without_approving_the_action() -> None:
    action = _action()
    repository = FakeProposalRepository(action)
    client = FakeGitHubClient()
    worker = GitOpsProposalWorker(
        "gitops-worker",
        repository,
        client,
        batch_size=10,
        lease_seconds=60,
        retry_seconds=30,
    )

    count = await worker.run_once(datetime(2026, 8, 9, 12, tzinfo=UTC))

    assert count == 1
    assert repository.failed is None
    assert repository.cancelled is None
    assert repository.completed is not None
    assert repository.completed[0] == action["id"]
    assert client.content is not None
    rollback = parse_manifest(client.content)
    assert rollback.spec.candidate is not None
    assert rollback.spec.candidate.traffic_percentage == 0


class StaleGitHubClient(FakeGitHubClient):
    async def get_file(self, connection: dict[str, Any]) -> GitHubRepositoryFile:
        return GitHubRepositoryFile(
            content=VALID_MANIFEST.replace("trafficPercentage: 10", "trafficPercentage: 20"),
            blob_sha="newer-blob-sha",
            revision="newer-commit-sha",
        )


@pytest.mark.asyncio
async def test_proposal_worker_cancels_instead_of_overwriting_a_newer_manifest() -> None:
    action = _action()
    repository = FakeProposalRepository(action)
    worker = GitOpsProposalWorker(
        "gitops-worker",
        repository,
        StaleGitHubClient(),
        batch_size=10,
        lease_seconds=60,
        retry_seconds=30,
    )

    assert await worker.run_once(datetime(2026, 8, 9, 12, tzinfo=UTC)) == 1
    assert repository.completed is None
    assert repository.failed is None
    assert repository.cancelled is not None
    assert "abstained" in repository.cancelled[1]


class FakeWebhookGitOps:
    def __init__(self, action_id: UUID):
        self.action_id = action_id

    def mark_pull_request_merged(
        self,
        owner: str,
        repository: str,
        number: int,
        merge_sha: str,
        actor: str,
        merged_at: datetime,
    ) -> dict[str, Any]:
        return {"action_id": self.action_id}

    def mark_pull_request_closed(self, owner: str, repository: str, number: int) -> dict[str, Any]:
        return {"action_id": self.action_id}

    def action_for_revision(self, owner: str, repository: str, revision: str):
        assert (owner, repository, revision) == ("example", "deployments", "merge-sha")
        return {
            "action_id": self.action_id,
            "pull_request_number": 42,
            "external_execution_id": "github-pr:example/deployments#42",
        }

    def connections_for_repository_branch(
        self, owner: str, repository: str, branch: str
    ) -> list[dict[str, Any]]:
        return []


class FakeExternalRemediation:
    def __init__(self) -> None:
        self.approved: tuple[Any, ...] | None = None
        self.rejected: tuple[Any, ...] | None = None
        self.completed: tuple[Any, ...] | None = None

    def approve_and_start_external(
        self,
        action_id: UUID,
        actor_id: str,
        reason: str,
        external_execution_id: str,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        self.approved = (action_id, actor_id, reason, external_execution_id, occurred_at)
        return {"status": "executing"}

    def reject_external(self, action_id: UUID, actor_id: str, reason: str) -> dict[str, Any]:
        self.rejected = (action_id, actor_id, reason)
        return {"status": "rejected"}

    def complete_external_execution(
        self,
        action_id: UUID,
        external_execution_id: str,
        status: str,
        details: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> dict[str, Any]:
        self.completed = (action_id, external_execution_id, status, details, occurred_at)
        return {"status": status}


@pytest.mark.asyncio
async def test_signed_merge_is_the_approval_and_deployment_success_completes_execution() -> None:
    action_id = uuid4()
    remediation = FakeExternalRemediation()
    service = GitHubWebhookService(FakeWebhookGitOps(action_id), remediation)
    repository = {"name": "deployments", "owner": {"login": "example"}}

    merge = await service.handle(
        "pull_request",
        {
            "action": "closed",
            "repository": repository,
            "sender": {"login": "risk-lead"},
            "pull_request": {
                "number": 42,
                "merged": True,
                "merge_commit_sha": "merge-sha",
                "merged_at": "2026-08-09T12:01:00Z",
                "merged_by": {"login": "risk-lead"},
            },
        },
    )
    execution = await service.handle(
        "deployment_status",
        {
            "repository": repository,
            "deployment": {
                "id": 91,
                "sha": "merge-sha",
                "environment": "production",
            },
            "deployment_status": {"state": "success", "log_url": "https://ci/run/91"},
        },
    )

    assert merge["status"] == "executing"
    assert remediation.approved is not None
    assert remediation.approved[0] == action_id
    assert remediation.approved[1] == "github:risk-lead"
    assert execution == {"status": "succeeded", "action_id": str(action_id)}
    assert remediation.completed is not None
    assert remediation.completed[:3] == (
        action_id,
        "github-pr:example/deployments#42",
        "succeeded",
    )


def test_manifest_model_can_be_registered_without_guessing_from_repository_code() -> None:
    model = parse_manifest(VALID_MANIFEST).spec.model
    definition = ModelDefinition(
        name=model.name,
        task=model.task,
        positive_class=model.positive_class,
        positive_actual=model.positive_actual,
        datahub_urn=model.datahub_urn,
    )

    assert definition.name == "fraud"
    assert definition.datahub_urn == "urn:li:mlModel:fraud"


@pytest.mark.asyncio
async def test_github_app_client_uses_installation_auth_and_repository_api_contracts() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM,
        serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/app/installations/123/access_tokens":
            token = request.headers["Authorization"].removeprefix("Bearer ")
            claims = jwt.decode(token, public_pem, algorithms=["RS256"])
            assert claims["iss"] == "99"
            return httpx.Response(201, json={"token": "installation-token"})
        assert request.headers["Authorization"] == "Bearer installation-token"
        if request.url.path.endswith("/git/ref/heads/main"):
            return httpx.Response(200, json={"object": {"sha": "commit-sha"}})
        if request.url.path.endswith("/contents/deployments/fraud.yaml"):
            assert request.url.params["ref"] == "commit-sha"
            return httpx.Response(
                200,
                json={
                    "content": base64.b64encode(VALID_MANIFEST.encode()).decode(),
                    "sha": "blob-sha",
                },
            )
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    client = GitHubAppClient(
        99,
        private_pem,
        transport=httpx.MockTransport(handler),
    )
    repository_file = await client.get_file(
        {
            "installation_id": 123,
            "repository_owner": "example",
            "repository_name": "deployments",
            "branch": "main",
            "manifest_path": "deployments/fraud.yaml",
        }
    )

    assert repository_file.content == VALID_MANIFEST
    assert repository_file.blob_sha == "blob-sha"
    assert repository_file.revision == "commit-sha"
    assert calls == [
        ("POST", "/app/installations/123/access_tokens"),
        ("GET", "/repos/example/deployments/git/ref/heads/main"),
        ("GET", "/repos/example/deployments/contents/deployments/fraud.yaml"),
    ]


@pytest.mark.asyncio
async def test_github_app_client_reports_reference_deployment_status() -> None:
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    deployment_requests: list[dict[str, Any]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/app/installations/123/access_tokens":
            return httpx.Response(201, json={"token": "installation-token"})
        payload = json.loads(request.content)
        deployment_requests.append(payload)
        if request.url.path == "/repos/example/deployments/deployments":
            return httpx.Response(201, json={"id": 71, "sha": "merge-sha"})
        if request.url.path == "/repos/example/deployments/deployments/71/statuses":
            return httpx.Response(201, json={"id": 72, "state": "success"})
        raise AssertionError(f"Unexpected GitHub request: {request.method} {request.url}")

    client = GitHubAppClient(99, private_pem, transport=httpx.MockTransport(handler))
    connection = {
        "installation_id": 123,
        "repository_owner": "example",
        "repository_name": "deployments",
    }
    deployment = await client.create_deployment(
        connection,
        revision="merge-sha",
        environment="production",
        payload={"source": "reference-reconciler"},
    )
    await client.create_deployment_status(
        connection,
        deployment_id=deployment.id,
        state="success",
        environment="production",
        description="Manifest applied",
        log_url="https://runtime.example.com/v1/runtime",
    )

    assert deployment.id == 71
    assert deployment.revision == "merge-sha"
    assert deployment_requests[0] == {
        "ref": "merge-sha",
        "environment": "production",
        "auto_merge": False,
        "required_contexts": [],
        "payload": {"source": "reference-reconciler"},
        "description": "Apply Histograph model deployment manifest",
        "production_environment": True,
    }
    assert deployment_requests[1]["state"] == "success"
    assert deployment_requests[1]["auto_inactive"] is True
