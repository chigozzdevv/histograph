from datetime import datetime
from typing import Any, Literal

from pydantic import Field, field_validator, model_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc

IncidentStatus = Literal["open", "investigating", "resolved", "closed"]


class RecoveryCheck(EventModel):
    name: str = Field(min_length=1, max_length=200)
    passed: Literal[True]
    details: dict[str, Any] = Field(default_factory=dict)


class RecoveryVerification(EventModel):
    status: Literal["verified"]
    verified_at: datetime
    checks: list[RecoveryCheck] = Field(min_length=1)

    @field_validator("verified_at")
    @classmethod
    def normalize_verified_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class IncidentTransition(EventModel):
    status: IncidentStatus
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_manual_closure_reason(self) -> "IncidentTransition":
        if self.status == "closed" and self.reason is None:
            raise ValueError("A reason is required when manually closing an incident")
        return self
