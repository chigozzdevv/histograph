from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from histograph.core.time import ensure_utc


class EventModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class Prediction(EventModel):
    prediction_id: str = Field(min_length=1, max_length=200)
    model: str = Field(min_length=1, max_length=200)
    version: str = Field(min_length=1, max_length=100)
    environment: str = Field(default="production", min_length=1, max_length=100)
    deployment: str | None = Field(default=None, max_length=200)
    observed_at: datetime
    predicted_class: str | None = Field(default=None, max_length=200)
    score: float | None = None
    features: dict[str, float | int | str | bool | None] = Field(default_factory=dict)
    tags: dict[str, str] = Field(default_factory=dict)
    latency_ms: float | None = Field(default=None, ge=0)
    error_state: str | None = Field(default=None, max_length=200)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


class Actual(EventModel):
    prediction_id: str = Field(min_length=1, max_length=200)
    actual: str | int | float | bool | None
    observed_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)


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
