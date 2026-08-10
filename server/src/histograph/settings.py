from functools import lru_cache
from pathlib import Path

from pydantic import AnyHttpUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_prefix="HISTOGRAPH_", extra="ignore")

    app_name: str = "Histograph"
    environment: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    postgres_dsn: str = "postgresql://histograph:histograph@localhost:5433/histograph"
    clickhouse_host: str = "localhost"
    clickhouse_port: int = 8124
    clickhouse_database: str = "histograph"
    clickhouse_user: str = "histograph"
    clickhouse_password: str = "histograph"
    datahub_gms_url: str = "http://localhost:8080"
    datahub_frontend_url: AnyHttpUrl | None = None
    datahub_gms_token: str | None = Field(default=None, repr=False)
    datahub_mcp_command: str = "uvx"
    datahub_mcp_package: str = "mcp-server-datahub==0.6.0"
    datahub_mcp_python: str | None = "3.13"
    datahub_mcp_timeout_seconds: float = 30.0
    datahub_mcp_mutations_enabled: bool = False
    approval_tokens: dict[str, str] = Field(default_factory=dict, repr=False)
    remediation_webhook_url: str | None = None
    remediation_webhook_token: str | None = Field(default=None, repr=False)
    remediation_callback_token: str | None = Field(default=None, repr=False)
    remediation_webhook_timeout_seconds: float = Field(default=30.0, gt=0, le=300)
    github_app_id: int | None = Field(default=None, gt=0)
    github_app_private_key: str | None = Field(default=None, repr=False)
    github_app_private_key_path: Path | None = None
    github_webhook_secret: str | None = Field(default=None, repr=False)
    github_configuration_token: str | None = Field(default=None, repr=False)
    github_api_url: str = "https://api.github.com"
    github_api_version: str = "2026-03-10"
    reference_control_token: str | None = Field(default=None, repr=False)
    playground_allowed_hosts: list[str] = Field(
        default_factory=lambda: ["runtime", "localhost", "127.0.0.1"]
    )
    playground_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    playground_rate_limit_per_minute: int = Field(default=60, ge=1, le=10_000)
    demo_control_token: str | None = Field(default=None, repr=False)
    demo_public_scenarios_enabled: bool = False
    demo_rate_limit_per_hour: int = Field(default=6, ge=1, le=1000)
    demo_api_url: str = "http://localhost:8000"
    demo_runtime_url: str = "http://localhost:8100"
    demo_replay_path: Path = Path("demo/artifacts/replay.parquet")
    demo_artifact_path: Path = Path("demo/artifacts/mobile_money_fraud.joblib")
    demo_sample_size: int = Field(default=1000, ge=100, le=5000)
    demo_outbox_wait_seconds: float = Field(default=30.0, ge=1, le=300)
    worker_poll_interval_seconds: float = Field(default=5.0, ge=0.1, le=300)
    worker_batch_size: int = Field(default=20, ge=1, le=500)
    worker_lease_seconds: int = Field(default=60, ge=10, le=3600)
    worker_retry_seconds: int = Field(default=30, ge=5, le=3600)


@lru_cache
def get_settings() -> Settings:
    return Settings()
