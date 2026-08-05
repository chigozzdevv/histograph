from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="HISTOGRAPH_", env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://histograph:histograph@localhost:5432/histograph"
    allowed_origins: list[str] = Field(
        default_factory=lambda: ["http://localhost:3000", "http://127.0.0.1:3000"]
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
