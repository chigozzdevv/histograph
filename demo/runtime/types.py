from datetime import datetime
from typing import Any

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc
from histograph.integrations.github.types import ModelDeploymentManifest
from histograph.models.types import JsonScalar


class ApplyManifestRequest(EventModel):
    revision: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1, max_length=1_000_000)


class PredictionRequest(EventModel):
    prediction_id: str = Field(min_length=1, max_length=200)
    features: dict[str, JsonScalar | None]
    observed_at: datetime | None = None

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class PredictionBatchRequest(EventModel):
    events: list[PredictionRequest] = Field(min_length=1, max_length=5000)


class PredictionResponse(EventModel):
    prediction_id: str
    model: str
    version: str
    deployment: str
    score: float
    predicted_class: str
    threshold: float
    observed_at: datetime


class PredictionBatchResponse(EventModel):
    events: list[PredictionResponse]


class ComparisonResponse(EventModel):
    stable: PredictionResponse
    candidate: PredictionResponse


class OutcomeRequest(EventModel):
    prediction_id: str = Field(min_length=1, max_length=200)
    actual: JsonScalar | None
    observed_at: datetime | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("observed_at")
    @classmethod
    def normalize_observed_at(cls, value: datetime | None) -> datetime | None:
        return ensure_utc(value) if value is not None else None


class OutcomeBatchRequest(EventModel):
    events: list[OutcomeRequest] = Field(min_length=1, max_length=5000)


class RuntimeStateView(EventModel):
    status: str
    revision: str | None
    manifest: ModelDeploymentManifest | None
    applied_at: datetime | None
    outbox_pending: int
