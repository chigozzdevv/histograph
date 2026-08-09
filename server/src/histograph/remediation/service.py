import hashlib
import json
from typing import Any, Protocol
from uuid import UUID

from histograph.remediation.types import ActionType, ApprovalDecision, RemediationProposal


class RemediationStore(Protocol):
    def propose(self, proposal: RemediationProposal) -> UUID: ...

    def decide(
        self, action_id: UUID, actor_id: str, decision: ApprovalDecision
    ) -> dict[str, Any] | None: ...


class RemediationAdapterSelector(Protocol):
    def adapter_for_target(self, target: dict[str, Any]) -> str | None: ...


class RemediationService:
    def __init__(
        self,
        repository: RemediationStore,
        adapter_selector: RemediationAdapterSelector | None = None,
    ):
        self._repository = repository
        self._adapter_selector = adapter_selector

    def propose_from_investigation(
        self, incident: dict[str, Any], report: dict[str, Any]
    ) -> UUID | None:
        if incident.get("status") not in {"open", "investigating"}:
            return None
        if report.get("status") != "probable_cause":
            return None
        root_cause = report.get("root_cause")
        if not isinstance(root_cause, dict):
            return None
        action_type = _action_type(root_cause)
        if action_type is None:
            return None
        incident_id = incident.get("id")
        if not isinstance(incident_id, UUID):
            incident_id = UUID(str(incident_id))
        target = _target(incident, report, root_cause)
        adapter = (
            self._adapter_selector.adapter_for_target(target)
            if self._adapter_selector is not None
            else None
        ) or "webhook"
        dedupe_key = hashlib.sha256(
            json.dumps(
                {
                    "incident_id": str(incident_id),
                    "action_type": action_type,
                    "target": target,
                },
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ).encode()
        ).hexdigest()
        return self._repository.propose(
            RemediationProposal(
                incident_id=incident_id,
                action_type=action_type,
                adapter=adapter,
                target=target,
                evidence={
                    "investigation_status": report["status"],
                    "root_cause": root_cause,
                    "datahub_model_urn": report.get("model", {}).get("urn"),
                    "recommended_action": report.get("recommended_action"),
                },
                dedupe_key=dedupe_key,
            )
        )

    def decide(
        self,
        action_id: UUID,
        actor_id: str,
        decision: ApprovalDecision,
    ) -> dict[str, Any] | None:
        return self._repository.decide(action_id, actor_id, decision)


def _action_type(root_cause: dict[str, Any]) -> ActionType | None:
    if root_cause.get("rollback_observed") is True:
        return None
    kind = root_cause.get("kind")
    if kind == "upstream_release":
        return "rollback_release"
    if kind == "model_release":
        return "stop_canary" if root_cause.get("strategy") == "canary" else "rollback_model"
    return None


def _target(
    incident: dict[str, Any], report: dict[str, Any], root_cause: dict[str, Any]
) -> dict[str, Any]:
    evidence = incident.get("evidence")
    trigger = evidence.get("trigger") if isinstance(evidence, dict) else None
    affected = trigger.get("affected_slice") if isinstance(trigger, dict) else None
    environment_value = affected.get("environment") if isinstance(affected, dict) else None
    environment = environment_value if isinstance(environment_value, str) else "production"
    return {
        "model": incident.get("model"),
        "version": root_cause.get("version") or incident.get("version"),
        "deployment": root_cause.get("deployment")
        or (affected.get("deployment") if isinstance(affected, dict) else None),
        "asset_urn": root_cause.get("asset_urn"),
        "asset_name": root_cause.get("asset_name"),
        "environment": environment,
        "datahub_model_urn": report.get("model", {}).get("urn"),
    }
