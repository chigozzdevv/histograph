from types import SimpleNamespace
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import ValidationError

from histograph.api.routes import remediation
from histograph.remediation.auth import StaticTokenAuthorizer
from histograph.remediation.service import RemediationService
from histograph.remediation.types import ApprovalDecision, ExecutionResult, RemediationProposal


class FakeRemediationStore:
    def __init__(self) -> None:
        self.proposals: list[RemediationProposal] = []
        self.decisions: list[tuple[UUID, str, ApprovalDecision]] = []

    def propose(self, proposal: RemediationProposal) -> UUID:
        self.proposals.append(proposal)
        return UUID(proposal.dedupe_key[:32])

    def decide(
        self, action_id: UUID, actor_id: str, decision: ApprovalDecision
    ) -> dict[str, Any] | None:
        self.decisions.append((action_id, actor_id, decision))
        return {"id": action_id, "status": "approved"}


def test_probable_canary_cause_proposes_one_deterministic_stop_action() -> None:
    incident_id = uuid4()
    incident = {
        "id": incident_id,
        "model": "fraud",
        "version": "v2",
        "status": "investigating",
        "evidence": {
            "trigger": {
                "affected_slice": {
                    "environment": "production",
                    "deployment": "fraud-production",
                }
            }
        },
    }
    report = {
        "status": "probable_cause",
        "model": {"urn": "urn:li:mlModel:fraud"},
        "root_cause": {
            "kind": "model_release",
            "deployment": "fraud-production",
            "version": "v2",
            "strategy": "canary",
        },
        "recommended_action": "Request approval to stop the canary.",
    }
    store = FakeRemediationStore()
    service = RemediationService(store)

    first = service.propose_from_investigation(incident, report)
    second = service.propose_from_investigation(incident, report)

    assert first == second
    assert [proposal.action_type for proposal in store.proposals] == [
        "stop_canary",
        "stop_canary",
    ]
    assert store.proposals[0].dedupe_key == store.proposals[1].dedupe_key
    assert store.proposals[0].target == {
        "model": "fraud",
        "version": "v2",
        "deployment": "fraud-production",
        "asset_urn": None,
        "asset_name": None,
        "environment": "production",
        "datahub_model_urn": "urn:li:mlModel:fraud",
    }


def test_action_is_not_proposed_before_probable_cause_or_after_recovery_confirmation() -> None:
    store = FakeRemediationStore()
    service = RemediationService(store)
    incident = {
        "id": uuid4(),
        "model": "fraud",
        "version": "v2",
        "status": "investigating",
    }
    root_cause = {"kind": "model_release", "strategy": "canary", "version": "v2"}

    assert (
        service.propose_from_investigation(
            incident, {"status": "insufficient_evidence", "root_cause": root_cause}
        )
        is None
    )
    assert (
        service.propose_from_investigation(
            incident, {"status": "confirmed_cause", "root_cause": root_cause}
        )
        is None
    )
    assert store.proposals == []


def test_approval_authorization_is_token_backed_and_does_not_trust_actor_input() -> None:
    authorizer = StaticTokenAuthorizer({"secret-token": "alice@example.com"})

    principal = authorizer.authorize("Bearer secret-token")

    assert principal.actor_id == "alice@example.com"
    assert principal.roles == ("remediation_approver",)
    with pytest.raises(PermissionError, match="valid remediation approver token"):
        authorizer.authorize("Bearer wrong-token")
    with pytest.raises(PermissionError, match="Bearer authorization"):
        authorizer.authorize(None)


def test_rejection_requires_an_auditable_reason() -> None:
    with pytest.raises(ValidationError, match="reason is required"):
        ApprovalDecision(decision="reject")

    decision = ApprovalDecision(
        decision="reject",
        reason="Rollback target has not passed compatibility checks",
    )

    assert decision.reason is not None


class FakeCallbackRepository:
    def __init__(self, action_id: UUID):
        self.action = {
            "id": action_id,
            "status": "executing",
            "external_execution_id": "provider-run-123",
        }
        self.result: ExecutionResult | None = None

    def get(self, action_id: UUID) -> dict[str, Any] | None:
        return self.action if action_id == self.action["id"] else None

    def complete_execution(
        self,
        action_id: UUID,
        result: ExecutionResult,
        completed_at=None,
    ) -> dict[str, Any] | None:
        assert action_id == self.action["id"]
        self.result = result
        self.action = {**self.action, "status": result.status}
        return self.action


def test_async_execution_callback_is_authenticated_and_bound_to_external_id() -> None:
    action_id = uuid4()
    repository = FakeCallbackRepository(action_id)
    app = FastAPI()
    app.state.remediation = repository
    app.state.settings = SimpleNamespace(remediation_callback_token="callback-secret")
    app.include_router(remediation.router)
    client = TestClient(app)
    payload = {
        "status": "succeeded",
        "external_execution_id": "provider-run-123",
        "details": {"provider_status": "completed"},
    }

    assert client.post(f"/v1/actions/{action_id}/result", json=payload).status_code == 401
    mismatch = client.post(
        f"/v1/actions/{action_id}/result",
        json={**payload, "external_execution_id": "different-run"},
        headers={"Authorization": "Bearer callback-secret"},
    )
    assert mismatch.status_code == 409
    response = client.post(
        f"/v1/actions/{action_id}/result",
        json=payload,
        headers={"Authorization": "Bearer callback-secret"},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "succeeded"
    assert repository.result is not None
    assert repository.result.external_execution_id == "provider-run-123"
