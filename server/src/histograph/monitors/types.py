from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


class Monitor(EventModel):
    model: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=100)
    signal: Literal[
        "performance", "feature_drift", "prediction_drift", "data_quality", "operational"
    ]
    metric: str = Field(min_length=1, max_length=100)
    operator: Literal["lt", "lte", "gt", "gte", "change"]
    threshold: float = Field(description="Threshold in the metric's native unit")
    baseline_window_minutes: int = Field(default=60, ge=1)
    evaluation_window_minutes: int = Field(default=15, ge=1)
    enabled: bool = True


class MonitorEvent(EventModel):
    monitor_id: UUID
    model: str
    version: str
    signal: str
    metric: str
    observed_value: float
    baseline_value: float | None = None
    threshold: float
    occurred_at: datetime
    affected_slice: dict[str, str] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
