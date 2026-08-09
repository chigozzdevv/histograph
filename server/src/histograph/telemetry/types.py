from datetime import datetime

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


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


class PredictionBatch(EventModel):
    events: list[Prediction] = Field(min_length=1, max_length=5000)
