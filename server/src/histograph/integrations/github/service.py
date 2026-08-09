import asyncio
import json
import posixpath
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

import yaml

from histograph.integrations.github.client import GitHubClient
from histograph.integrations.github.manifest import parse_manifest
from histograph.integrations.github.repository import GitOpsRepository
from histograph.integrations.github.types import (
    CreatedPullRequest,
    GitHubConnectionCreate,
    ModelDeploymentManifest,
    ResolvedModelInterface,
)
from histograph.models.repository import ModelRepository
from histograph.models.types import ModelDefinition


class ExternalRemediationStore(Protocol):
    def approve_and_start_external(
        self,
        action_id: UUID,
        actor_id: str,
        reason: str,
        external_execution_id: str,
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None: ...

    def reject_external(
        self, action_id: UUID, actor_id: str, reason: str
    ) -> dict[str, Any] | None: ...

    def complete_external_execution(
        self,
        action_id: UUID,
        external_execution_id: str,
        status: str,
        details: dict[str, Any],
        occurred_at: datetime | None = None,
    ) -> dict[str, Any] | None: ...


class GitHubWebhookStore(Protocol):
    def mark_pull_request_merged(
        self,
        owner: str,
        repository: str,
        number: int,
        merge_sha: str,
        actor: str,
        merged_at: datetime,
    ) -> dict[str, Any] | None: ...

    def mark_pull_request_closed(
        self, owner: str, repository: str, number: int
    ) -> dict[str, Any] | None: ...

    def action_for_revision(
        self, owner: str, repository: str, revision: str
    ) -> dict[str, Any] | None: ...

    def connections_for_repository_branch(
        self, owner: str, repository: str, branch: str
    ) -> list[dict[str, Any]]: ...


class GitHubIntegrationService:
    def __init__(
        self,
        repository: GitOpsRepository,
        models: ModelRepository,
        client: GitHubClient | None,
    ):
        self._repository = repository
        self._models = models
        self._client = client

    def create_connection(self, connection: GitHubConnectionCreate) -> UUID:
        return self._repository.save_connection(connection)

    async def sync(self, connection_id: UUID) -> dict[str, Any]:
        connection = self._repository.get_connection(connection_id)
        if connection is None:
            raise LookupError("GitHub connection not found")
        if not connection["enabled"]:
            raise ValueError("GitHub connection is disabled")
        if self._client is None:
            raise RuntimeError("GitHub App credentials are not configured")
        try:
            repository_file = await self._client.get_file(connection)
            manifest = parse_manifest(repository_file.content)
            interface = await self._resolve_interface(
                connection, manifest, repository_file.revision
            )
            model = manifest.spec.model
            self._models.save(
                ModelDefinition(
                    name=model.name,
                    task=model.task,
                    positive_class=model.positive_class,
                    positive_actual=model.positive_actual,
                    datahub_urn=model.datahub_urn,
                )
            )
            deployment_id = self._repository.record_sync(
                connection_id,
                manifest,
                revision=repository_file.revision,
                manifest_sha=repository_file.blob_sha,
                content=repository_file.content,
                interface=interface,
            )
            deployment = self._repository.get_deployment(deployment_id)
            if deployment is None:
                raise RuntimeError("Imported GitOps deployment could not be read back")
            return deployment
        except Exception as error:
            self._repository.fail_sync(connection_id, str(error))
            raise

    async def _resolve_interface(
        self,
        connection: dict[str, Any],
        manifest: ModelDeploymentManifest,
        revision: str,
    ) -> ResolvedModelInterface | None:
        declared = manifest.spec.interface
        if declared is None:
            return None
        if self._client is None:
            raise RuntimeError("GitHub App credentials are not configured")
        manifest_path = str(connection["manifest_path"])
        paths = [
            _resolve_repository_path(manifest_path, declared.input_schema.path),
            _resolve_repository_path(manifest_path, declared.output_schema.path),
            _resolve_repository_path(manifest_path, declared.examples.path),
        ]
        get_repository_file = getattr(self._client, "get_repository_file", None)
        if get_repository_file is None:
            raise RuntimeError("GitHub client cannot load referenced manifest resources")
        input_file, output_file, examples_file = await asyncio.gather(
            *(get_repository_file(connection, path, revision=revision) for path in paths)
        )
        if any(
            repository_file.revision != revision
            for repository_file in (input_file, output_file, examples_file)
        ):
            raise RuntimeError("GitHub returned deployment resources from mixed revisions")
        input_schema = _json_object(input_file.content, "input schema")
        output_schema = _json_object(output_file.content, "output schema")
        try:
            examples_payload = yaml.safe_load(examples_file.content)
        except yaml.YAMLError as error:
            raise ValueError(f"Playground examples are not valid YAML: {error}") from error
        examples = examples_payload.get("examples") if isinstance(examples_payload, dict) else None
        if not isinstance(examples, list) or not examples:
            raise ValueError("Playground examples must contain a non-empty examples list")
        for example in examples:
            if not isinstance(example, dict) or not isinstance(example.get("input"), dict):
                raise ValueError("Each playground example must contain an input object")
        return ResolvedModelInterface(
            input_schema=input_schema,
            output_schema=output_schema,
            examples=examples,
        )

    async def create_demo_reset(
        self,
        deployment_id: UUID,
        run_id: UUID,
        baseline_content: str,
    ) -> CreatedPullRequest:
        deployment = self._repository.get_deployment(deployment_id)
        if deployment is None:
            raise LookupError("Deployment not found")
        if self._client is None:
            raise RuntimeError("GitHub App credentials are not configured")
        baseline = parse_manifest(baseline_content)
        if (
            baseline.metadata.name != deployment["deployment"]
            or baseline.spec.model.name != deployment["model"]
            or baseline.spec.environment != deployment["environment"]
        ):
            raise ValueError("Saved demo baseline does not match the imported deployment")
        if baseline.spec.candidate is None or baseline.spec.candidate.traffic_percentage <= 0:
            raise ValueError("Saved demo baseline has no active candidate release")
        return await self._client.create_pull_request(
            deployment,
            head_branch=f"histograph/demo-reset-{run_id}",
            content=baseline_content,
            title=f"fix: reset {baseline.metadata.name} demo canary",
            body=(
                "Restore the pre-scenario canary manifest after Histograph verified recovery. "
                "Merging this pull request starts a fresh, observable deployment; it does not "
                "change the evidence retained for the completed incident."
            ),
        )


class GitHubWebhookService:
    def __init__(
        self,
        gitops: GitHubWebhookStore,
        remediation: ExternalRemediationStore,
        integration: GitHubIntegrationService | None = None,
    ):
        self._gitops = gitops
        self._remediation = remediation
        self._integration = integration

    async def handle(self, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
        if event_type == "pull_request":
            return self._pull_request(payload)
        if event_type == "deployment_status":
            return self._deployment_status(payload)
        if event_type == "push":
            return await self._push(payload)
        return {"status": "ignored", "event": event_type}

    async def _push(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self._integration is None:
            return {"status": "ignored", "event": "push"}
        ref = payload.get("ref")
        if not isinstance(ref, str) or not ref.startswith("refs/heads/"):
            return {"status": "ignored", "event": "push"}
        branch = ref.removeprefix("refs/heads/")
        owner, repository = _repository(payload)
        connections = self._gitops.connections_for_repository_branch(owner, repository, branch)
        for connection in connections:
            await self._integration.sync(connection["id"])
        return {"status": "synced", "connections": len(connections)}

    def _pull_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        if payload.get("action") != "closed":
            return {"status": "ignored", "event": "pull_request"}
        owner, repository = _repository(payload)
        pull_request = _object(payload, "pull_request")
        number = pull_request.get("number")
        if not isinstance(number, int):
            raise ValueError("GitHub pull request webhook has no numeric pull request number")
        sender = _login(payload.get("sender"))
        if pull_request.get("merged") is not True:
            record = self._gitops.mark_pull_request_closed(owner, repository, number)
            if record is None:
                return {"status": "ignored", "event": "pull_request"}
            self._remediation.reject_external(
                record["action_id"],
                f"github:{sender}",
                f"GitHub rollback pull request #{number} was closed without merging",
            )
            return {"status": "rejected", "action_id": str(record["action_id"])}

        merge_sha = pull_request.get("merge_commit_sha")
        if not isinstance(merge_sha, str) or not merge_sha:
            raise ValueError("Merged GitHub pull request has no merge commit SHA")
        merged_by = _login(pull_request.get("merged_by")) or sender
        merged_at = _timestamp(pull_request.get("merged_at"))
        record = self._gitops.mark_pull_request_merged(
            owner, repository, number, merge_sha, merged_by, merged_at
        )
        if record is None:
            return {"status": "ignored", "event": "pull_request"}
        external_id = _external_id(owner, repository, number)
        self._remediation.approve_and_start_external(
            record["action_id"],
            f"github:{merged_by}",
            f"Merged GitHub rollback pull request #{number} at {merge_sha}",
            external_id,
            merged_at,
        )
        return {
            "status": "executing",
            "action_id": str(record["action_id"]),
            "external_execution_id": external_id,
        }

    def _deployment_status(self, payload: dict[str, Any]) -> dict[str, Any]:
        owner, repository = _repository(payload)
        deployment = _object(payload, "deployment")
        status_payload = _object(payload, "deployment_status")
        revision = deployment.get("sha")
        state = status_payload.get("state")
        if not isinstance(revision, str) or not revision:
            raise ValueError("GitHub deployment status has no deployment revision")
        if state not in {"success", "failure", "error"}:
            return {"status": "ignored", "event": "deployment_status"}
        record = self._gitops.action_for_revision(owner, repository, revision)
        if record is None:
            return {"status": "ignored", "event": "deployment_status"}
        external_id = record.get("external_execution_id") or _external_id(
            owner, repository, int(record["pull_request_number"])
        )
        terminal = "succeeded" if state == "success" else "failed"
        action = self._remediation.complete_external_execution(
            record["action_id"],
            str(external_id),
            terminal,
            {
                "source": "github_deployment_status",
                "state": state,
                "deployment_id": deployment.get("id"),
                "environment": deployment.get("environment"),
                "log_url": status_payload.get("log_url") or status_payload.get("target_url"),
                "revision": revision,
            },
            _optional_timestamp(status_payload.get("created_at")),
        )
        if action is None:
            raise RuntimeError("GitHub deployment action disappeared during completion")
        return {"status": terminal, "action_id": str(record["action_id"])}


def _repository(payload: dict[str, Any]) -> tuple[str, str]:
    repository = _object(payload, "repository")
    owner = _login(repository.get("owner"))
    name = repository.get("name")
    if not owner or not isinstance(name, str) or not name:
        raise ValueError("GitHub webhook does not identify a repository")
    return owner, name


def _object(payload: dict[str, Any], key: str) -> dict[str, Any]:
    value = payload.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"GitHub webhook has no {key} object")
    return value


def _login(value: Any) -> str:
    if not isinstance(value, dict):
        return "unknown"
    login = value.get("login")
    return login if isinstance(login, str) and login else "unknown"


def _timestamp(value: Any) -> datetime:
    if not isinstance(value, str):
        raise ValueError("GitHub pull request merge has no timestamp")
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise ValueError("GitHub pull request merge timestamp is invalid") from error


def _optional_timestamp(value: Any) -> datetime | None:
    return _timestamp(value) if isinstance(value, str) else None


def _external_id(owner: str, repository: str, number: int) -> str:
    return f"github-pr:{owner}/{repository}#{number}"


def _resolve_repository_path(manifest_path: str, resource_path: str) -> str:
    resolved = posixpath.normpath(posixpath.join(posixpath.dirname(manifest_path), resource_path))
    if resolved == ".." or resolved.startswith("../") or resolved.startswith("/"):
        raise ValueError("Manifest resources must remain inside the repository")
    return resolved


def _json_object(content: str, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(content)
    except json.JSONDecodeError as error:
        raise ValueError(f"Deployment {label} is not valid JSON: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError(f"Deployment {label} must contain one JSON object")
    return payload
