from functools import lru_cache
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HISTOGRAPH_", env_file=".env", extra="ignore")

    environment: Literal["local", "test", "staging", "production"] = "local"
    database_url: str = "postgresql+asyncpg://histograph:histograph@localhost:5432/histograph"
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )
    encryption_keys: SecretStr
    token_pepper: SecretStr
    bootstrap_token: SecretStr | None = None
    oidc_issuer: str | None = None
    oidc_audience: str | None = None
    temporal_address: str = "localhost:7233"
    temporal_namespace: str = "default"
    temporal_task_queue: str = "histograph-runs"
    s3_endpoint_url: str = "http://localhost:9000"
    s3_bucket: str = "histograph-evidence"
    s3_region: str = "us-east-1"
    s3_access_key_id: SecretStr | None = None
    s3_secret_access_key: SecretStr | None = None
    github_app_id: str | None = None
    github_private_key: SecretStr | None = None
    github_webhook_secret: SecretStr | None = None
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    public_app_url: str = "http://localhost:3000"

    @model_validator(mode="after")
    def validate_integrations(self) -> "Settings":
        github_values = (
            self.github_app_id,
            self.github_private_key.get_secret_value() if self.github_private_key else None,
            self.github_webhook_secret.get_secret_value() if self.github_webhook_secret else None,
        )
        configured_github_values = [bool(value) for value in github_values]
        if any(configured_github_values) and not all(configured_github_values):
            raise ValueError(
                "GitHub App ID, private key, and webhook secret must be configured together"
            )
        if bool(self.oidc_issuer) != bool(self.oidc_audience):
            raise ValueError("OIDC issuer and audience must be configured together")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
