from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


class Deployment(EventModel):
    deployment: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    environment: str = Field(default="production", min_length=1, max_length=100)
    strategy: Literal["standard", "canary", "blue_green"] = "standard"
    traffic_percentage: float = Field(default=100, ge=0, le=100)
    status: Literal["starting", "monitoring", "active", "stopped", "rolled_back"]
    occurred_at: datetime
    endpoint: str | None = Field(default=None, max_length=500)

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
