from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


class Actual(EventModel):
    prediction_id: str = Field(min_length=1, max_length=200)
    actual: str | int | float | bool | None
    observed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
