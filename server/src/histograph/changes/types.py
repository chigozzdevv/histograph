from datetime import datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from pydantic import Field, field_validator

from histograph.core.events import EventModel
from histograph.core.time import ensure_utc


class Change(EventModel):
    id: UUID = Field(default_factory=uuid4)
    asset_urn: str = Field(min_length=1, max_length=1000)
    asset_name: str = Field(min_length=1, max_length=300)
    asset_type: Literal["dataset", "data_job", "feature", "model", "deployment"]
    version: str = Field(min_length=1, max_length=200)
    environment: str = Field(default="production", min_length=1, max_length=100)
    change_type: Literal["code", "configuration", "schema", "data", "rollback"]
    status: Literal["applied", "rolled_back", "failed"]
    occurred_at: datetime
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("occurred_at")
    @classmethod
    def normalize_occurred_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)
