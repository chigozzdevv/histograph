from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from histograph_api.schemas.common import ApiModel


class CreateScheduleRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    cron_expression: str = Field(min_length=5, max_length=160)
    timezone: str
    concurrency_policy: Literal["skip", "queue", "replace"] = "skip"
    suite_id: str | None = None
    protected_question_id: str | None = None

    @model_validator(mode="after")
    def validate_selection(self) -> "CreateScheduleRequest":
        if (self.suite_id is None) == (self.protected_question_id is None):
            raise ValueError("Select exactly one suite or protected question")
        return self


class ScheduleResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    suite_id: str | None
    protected_question_id: str | None
    name: str
    cron_expression: str
    timezone: str
    concurrency_policy: str
    active: bool
    temporal_schedule_id: str
    created_by: str
    created_at: datetime
    updated_at: datetime


class MetadataEventRequest(ApiModel):
    source: str = Field(min_length=1, max_length=120)
    idempotency_key: str = Field(min_length=1, max_length=512)
    datahub_connection_id: str
    entity_urn: str = Field(min_length=1, max_length=1024)
    event_type: str = Field(min_length=1, max_length=160)
    aspect_name: str | None = Field(default=None, max_length=255)
    aspect_version: int | None = Field(default=None, ge=0)
    cursor: str | None = Field(default=None, max_length=512)
    payload: dict


class MetadataEventResponse(ApiModel):
    id: str
    status: str
    fingerprint: str
    run_id: str | None
    created_at: datetime
