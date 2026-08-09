from datetime import datetime
from typing import Literal
from uuid import UUID, uuid4

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
    feature: str | None = Field(default=None, min_length=1, max_length=200)
    reference_version: str | None = Field(default=None, min_length=1, max_length=100)
    operator: Literal["lt", "lte", "gt", "gte", "change", "decrease", "increase"]
    threshold: float = Field(description="Threshold in the metric's native unit")
    baseline_window_minutes: int = Field(default=60, ge=1)
    evaluation_window_minutes: int = Field(default=15, ge=1)
    minimum_sample_size: int = Field(default=30, ge=2)
    check_interval_seconds: int = Field(default=60, ge=5, le=86_400)
    enabled: bool = True

    @model_validator(mode="after")
    def validate_metric(self) -> "Monitor":
        if self.signal == "feature_drift":
            if self.metric != "psi":
                raise ValueError("Feature drift monitors currently support only the psi metric")
            if self.operator not in {"gt", "gte"}:
                raise ValueError("PSI monitors require the gt or gte operator")
            if self.feature is None:
                raise ValueError("Feature drift monitors require a configured feature")
            if self.reference_version is not None:
                raise ValueError("Feature drift monitors cannot configure a reference version")
            return self

        if self.feature is not None:
            raise ValueError("Performance monitors cannot configure a feature")
        if self.reference_version is not None:
            if self.version is None:
                raise ValueError("Canary comparisons require an explicit candidate version")
            if self.reference_version == self.version:
                raise ValueError("Candidate and reference versions must differ")

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
        if self.operator == "decrease" and self.metric in {
            "false_positive_rate",
            "false_negative_rate",
        }:
            raise ValueError(f"Use the increase operator to detect degradation in {self.metric}")
        if self.operator == "increase" and self.metric not in {
            "false_positive_rate",
            "false_negative_rate",
        }:
            raise ValueError(f"Use the decrease operator to detect degradation in {self.metric}")
        return self


class MonitorEvent(EventModel):
    id: UUID = Field(default_factory=uuid4)
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
