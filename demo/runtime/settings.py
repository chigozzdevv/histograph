from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from demo import ARTIFACT_ROOT, ROOT


class ReferenceRuntimeSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="HISTOGRAPH_REFERENCE_",
        extra="ignore",
    )

    host: str = "0.0.0.0"
    port: int = Field(default=8100, ge=1, le=65535)
    workspace_root: Path = ROOT.parent
    state_path: Path = ARTIFACT_ROOT / "reference_runtime.sqlite3"
    reconciler_state_path: Path = ARTIFACT_ROOT / "reference_reconciler.sqlite3"
    histograph_api_url: str = "http://localhost:8000"
    control_token: str | None = Field(default=None, repr=False)
    telemetry_poll_seconds: float = Field(default=1.0, ge=0.1, le=60)
    telemetry_batch_size: int = Field(default=100, ge=1, le=1000)
    telemetry_retry_seconds: int = Field(default=5, ge=1, le=300)

    github_installation_id: int | None = Field(default=None, gt=0)
    github_repository_owner: str | None = None
    github_repository_name: str | None = None
    github_branch: str = "main"
    github_manifest_path: str = ".histograph/deployments/mobile-money-fraud.yaml"
    reconciler_poll_seconds: float = Field(default=5.0, ge=1, le=300)
    runtime_url: str = "http://localhost:8100"
