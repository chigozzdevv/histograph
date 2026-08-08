from typing import Literal

from pydantic import Field, model_validator

from histograph.core.events import EventModel

IncidentStatus = Literal["open", "investigating", "resolved", "closed"]


class IncidentTransition(EventModel):
    status: IncidentStatus
    reason: str | None = Field(default=None, min_length=1, max_length=2000)

    @model_validator(mode="after")
    def require_resolution_reason(self) -> "IncidentTransition":
        if self.status in {"resolved", "closed"} and self.reason is None:
            raise ValueError("A reason is required when resolving or closing an incident")
        return self
