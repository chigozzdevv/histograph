from typing import Any, Literal
from uuid import UUID

from pydantic import Field, model_validator

from histograph.core.events import EventModel

ActionType = Literal["stop_canary", "rollback_model", "rollback_release"]
ActionStatus = Literal[
    "proposed",
    "approved",
    "rejected",
    "executing",
    "succeeded",
    "failed",
    "cancelled",
]


class RemediationProposal(EventModel):
    incident_id: UUID
    action_type: ActionType
    adapter: str = Field(default="webhook", min_length=1, max_length=100)
    target: dict[str, Any]
    evidence: dict[str, Any]
    dedupe_key: str = Field(min_length=64, max_length=64)


class ApprovalDecision(EventModel):
    decision: Literal["approve", "reject"]
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_rejection_reason(self) -> "ApprovalDecision":
        if self.decision == "reject" and self.reason is None:
            raise ValueError("A reason is required when rejecting a remediation action")
        return self


class ExecutionResult(EventModel):
    status: Literal["accepted", "succeeded", "failed"]
    external_execution_id: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)


class ExecutionCallback(EventModel):
    status: Literal["succeeded", "failed"]
    external_execution_id: str = Field(min_length=1, max_length=500)
    details: dict[str, Any] = Field(default_factory=dict)
