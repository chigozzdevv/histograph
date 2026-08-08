from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import Field, field_validator, model_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


class Monitor(EventModel):
    model: str = Field(min_length=1, max_length=200)
    version: str | None = Field(default=None, max_length=100)
    environment: str = Field(default="production", min_length=1, max_length=100)
    deployment: str | None = Field(default=None, max_length=200)
    signal: Literal["performance", "feature_drift"]
    metric: str = Field(min_length=1, max_length=100)
    operator: Literal["lt", "lte", "gt", "gte", "change"]
    threshold: float = Field(description="Threshold in the metric's native unit")
    baseline_window_minutes: int = Field(default=60, ge=1)
    evaluation_window_minutes: int = Field(default=15, ge=1)
    minimum_sample_size: int = Field(default=30, ge=2)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_metric(self) -> "Monitor":
        if self.signal == "feature_drift":
            if self.metric != "psi":
                raise ValueError("Feature drift monitors currently support only the psi metric")
            if self.operator not in {"gt", "gte"}:
                raise ValueError("PSI monitors require the gt or gte operator")
            return self

        supported = {
            "accuracy",
            "precision",
            "recall",
            "f1",
            "false_positive_rate",
            "false_negative_rate",
        }
        if self.metric not in supported:
            raise ValueError(
                f"Binary performance metric must be one of: {', '.join(sorted(supported))}"
            )
        return self


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
