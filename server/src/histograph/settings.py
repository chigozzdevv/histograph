from functools import lru_cache

from pydantic import Field
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
    datahub_gms_token: str | None = Field(default=None, repr=False)
    datahub_mcp_command: str = "uvx"
    datahub_mcp_package: str = "mcp-server-datahub==0.6.0"
    datahub_mcp_python: str | None = "3.13"
    datahub_mcp_timeout_seconds: float = 30.0
    datahub_mcp_mutations_enabled: bool = False


@lru_cache
def get_settings() -> Settings:
    return Settings()
