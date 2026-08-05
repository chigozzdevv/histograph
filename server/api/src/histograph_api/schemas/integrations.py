from datetime import datetime
from typing import Literal

from pydantic import AnyHttpUrl, Field, SecretStr, model_validator

from histograph_api.schemas.common import ApiModel


class CreateDataHubConnectionRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    mode: Literal["cloud", "self_hosted"]
    endpoint_url: AnyHttpUrl
    mcp_url: AnyHttpUrl
    deployment_id: str | None = Field(default=None, max_length=255)
    secret_location: Literal["managed"] = "managed"
    token: SecretStr | None = None

    @model_validator(mode="after")
    def validate_token_location(self) -> "CreateDataHubConnectionRequest":
        if self.secret_location == "managed" and self.token is None:
            raise ValueError("Managed DataHub connections require a token")
        return self


class DataHubConnectionResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    name: str
    mode: str
    endpoint_url: str
    mcp_url: str
    deployment_id: str | None
    secret_location: str
    status: str
    capabilities_json: dict
    version: int
    active: bool
    last_verified_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class CreateAgentTargetRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    adapter_type: Literal["datahub_analytics_agent"] = "datahub_analytics_agent"
    base_url: AnyHttpUrl
    engine_name: str = Field(min_length=1, max_length=255)
    secret_location: Literal["managed"] = "managed"
    token: SecretStr | None = None


class AgentTargetResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    name: str
    adapter_type: str
    base_url: str
    engine_name: str
    secret_location: str
    status: str
    capabilities_json: dict
    prompt_fingerprint: str | None
    model_identifiers_json: list[str]
    version: int
    active: bool
    last_verified_at: datetime | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class IntegrationTestResponse(ApiModel):
    status: str
    capabilities: dict
    verified_at: datetime
