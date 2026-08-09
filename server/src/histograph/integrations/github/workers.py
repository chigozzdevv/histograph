import logging
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from histograph.integrations.github.client import GitHubClient
from histograph.integrations.github.manifest import render_rollback
from histograph.integrations.github.types import CreatedPullRequest

logger = logging.getLogger(__name__)


class GitOpsProposalStore(Protocol):
    def claim_pull_request_proposals(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def complete_pull_request(self, action_id: UUID, result: CreatedPullRequest) -> None: ...

    def fail_pull_request(
        self,
        action_id: UUID,
        error: str,
        failed_at: datetime,
        retry_seconds: int,
    ) -> None: ...

    def cancel_stale_proposal(self, action_id: UUID, reason: str) -> None: ...


class GitOpsProposalWorker:
    def __init__(
        self,
        worker_id: str,
        repository: GitOpsProposalStore,
        client: GitHubClient | None,
        *,
        batch_size: int,
        lease_seconds: int,
        retry_seconds: int,
    ):
        self._worker_id = worker_id
        self._repository = repository
        self._client = client
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds

    async def run_once(self, now: datetime) -> int:
        records = self._repository.claim_pull_request_proposals(
            self._worker_id, now, self._batch_size, self._lease_seconds
        )
        for action in records:
            action_id = action["id"]
            try:
                if self._client is None:
                    raise RuntimeError("GitHub App credentials are not configured")
                current = await self._client.get_file(action)
                if current.blob_sha != action["manifest_sha"]:
                    self._repository.cancel_stale_proposal(
                        action_id,
                        "Deployment manifest changed after the incident investigation; "
                        "Histograph abstained from opening a stale rollback PR",
                    )
                    continue
                content = render_rollback(action["manifest_content"], action)
                deployment = action["target"].get("deployment") or "deployment"
                title = f"fix: roll back {deployment} after Histograph incident"
                result = await self._client.create_pull_request(
                    action,
                    head_branch=action["head_branch"],
                    content=content,
                    title=title,
                    body=_pull_request_body(action),
                )
                self._repository.complete_pull_request(action_id, result)
            except Exception as error:
                logger.exception(
                    "GitOps rollback pull request failed", extra={"action_id": str(action_id)}
                )
                self._repository.fail_pull_request(action_id, str(error), now, self._retry_seconds)
        return len(records)


def _pull_request_body(action: dict[str, Any]) -> str:
    target = action.get("target") or {}
    evidence = action.get("evidence") or {}
    return "\n".join(
        [
            "## Histograph remediation proposal",
            "",
            f"- Action: `{action['action_type']}`",
            f"- Incident: `{action['incident_id']}`",
            f"- Model: `{target.get('model')}`",
            f"- Version: `{target.get('version')}`",
            f"- Deployment: `{target.get('deployment')}`",
            f"- Investigation status: `{evidence.get('investigation_status')}`",
            "",
            (
                "Merging this pull request is the authorized remediation decision. "
                "Histograph will keep the incident open until runtime recovery is "
                "independently verified."
            ),
        ]
    )
