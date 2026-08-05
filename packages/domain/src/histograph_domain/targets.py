from pydantic import AnyHttpUrl, Field, SecretStr

from histograph_domain.base import DomainModel


class DataHubConnection(DomainModel):
    mcp_url: AnyHttpUrl
    token: SecretStr
    timeout_seconds: float = Field(default=30, gt=0, le=300)


class AnalyticsAgentTarget(DomainModel):
    base_url: AnyHttpUrl
    engine_name: str = Field(min_length=1)
    token: SecretStr | None = None
    timeout_seconds: float = Field(default=180, gt=0, le=900)
