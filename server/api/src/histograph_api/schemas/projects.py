from datetime import datetime
from typing import Literal

from pydantic import Field, field_validator

from histograph_api.schemas.common import ApiModel


class CreateProjectRequest(ApiModel):
    organization_id: str
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    environment: Literal["development", "staging", "production"]
    timezone: str = "UTC"
    retention_days: int = Field(default=90, ge=7, le=3650)
    max_concurrent_runs: int = Field(default=4, ge=1, le=100)

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError as error:
            raise ValueError("Unknown IANA timezone") from error
        return value


class UpdateProjectRequest(ApiModel):
    name: str | None = Field(default=None, min_length=1, max_length=160)
    timezone: str | None = None
    retention_days: int | None = Field(default=None, ge=7, le=3650)
    max_concurrent_runs: int | None = Field(default=None, ge=1, le=100)
    default_trigger_policy: dict | None = None


class ProjectResponse(ApiModel):
    id: str
    organization_id: str
    name: str
    slug: str
    environment: str
    timezone: str
    retention_days: int
    max_concurrent_runs: int
    default_trigger_policy_json: dict
    created_at: datetime
    updated_at: datetime
