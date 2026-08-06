from datetime import datetime
from typing import Literal

from pydantic import Field

from histograph.api.schemas.common import ApiModel


class CreateOrganizationRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    owner_email: str = Field(min_length=3, max_length=320)
    owner_display_name: str = Field(min_length=1, max_length=160)


class OrganizationResponse(ApiModel):
    id: str
    name: str
    slug: str
    created_at: datetime
    updated_at: datetime


class IssueServiceIdentityRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    project_id: str | None = None
    scopes: tuple[
        Literal[
            "control-plane:write",
            "metadata-events:write",
        ],
        ...,
    ] = Field(min_length=1)
    expires_at: datetime | None = None


class IssuedServiceIdentityResponse(ApiModel):
    id: str
    name: str
    project_id: str | None
    token: str
    token_prefix: str
    scopes: tuple[str, ...]
    expires_at: datetime | None
