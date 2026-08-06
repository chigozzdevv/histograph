from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from histograph.api.database.base import Base
from histograph.api.database.models.common import (
    ConnectionStatus,
    ProjectEnvironment,
    SecretLocation,
    SoftDeleteMixin,
    TimestampMixin,
    enum_type,
    json_type,
    new_id,
)


class ProjectRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "projects"
    __table_args__ = (UniqueConstraint("organization_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    environment: Mapped[ProjectEnvironment] = mapped_column(
        enum_type(ProjectEnvironment, "project_environment"), nullable=False
    )
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, default="UTC")
    retention_days: Mapped[int] = mapped_column(Integer, nullable=False, default=90)
    max_concurrent_runs: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    default_trigger_policy_json: Mapped[dict] = mapped_column(
        json_type, nullable=False, default=dict
    )


class GitHubInstallationRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "github_installations"
    __table_args__ = (UniqueConstraint("installation_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    installation_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    account_login: Mapped[str] = mapped_column(String(255), nullable=False)
    account_type: Mapped[str] = mapped_column(String(40), nullable=False)
    repository_selection: Mapped[str] = mapped_column(String(40), nullable=False)
    permissions_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    suspended_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RepositoryConnectionRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "repository_connections"
    __table_args__ = (
        UniqueConstraint("project_id", "repository_id"),
        Index(
            "ix_repository_connections_installation_repo", "github_installation_id", "repository_id"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    github_installation_id: Mapped[str] = mapped_column(
        ForeignKey("github_installations.id", ondelete="CASCADE"), nullable=False
    )
    repository_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    owner: Mapped[str] = mapped_column(String(255), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str] = mapped_column(String(520), nullable=False)
    default_branch: Mapped[str] = mapped_column(String(255), nullable=False)
    configuration_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class DataHubConnectionRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "datahub_connections"
    __table_args__ = (
        UniqueConstraint("project_id", "version"),
        Index("ix_datahub_connections_project_active", "project_id", "active"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    endpoint_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    mcp_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    deployment_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_location: Mapped[SecretLocation] = mapped_column(
        enum_type(SecretLocation, "datahub_secret_location"), nullable=False
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        enum_type(ConnectionStatus, "datahub_connection_status"), nullable=False
    )
    capabilities_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentTargetRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "agent_targets"
    __table_args__ = (UniqueConstraint("project_id", "name", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    adapter_type: Mapped[str] = mapped_column(String(80), nullable=False)
    base_url: Mapped[str] = mapped_column(String(2048), nullable=False)
    engine_name: Mapped[str] = mapped_column(String(255), nullable=False)
    encrypted_credentials: Mapped[str | None] = mapped_column(Text, nullable=True)
    secret_location: Mapped[SecretLocation] = mapped_column(
        enum_type(SecretLocation, "agent_secret_location"), nullable=False
    )
    status: Mapped[ConnectionStatus] = mapped_column(
        enum_type(ConnectionStatus, "agent_target_status"), nullable=False
    )
    capabilities_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    prompt_fingerprint: Mapped[str | None] = mapped_column(String(128), nullable=True)
    model_identifiers_json: Mapped[list[str]] = mapped_column(
        json_type, nullable=False, default=list
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    last_verified_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class RunnerPoolRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "runner_pools"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    mode: Mapped[str] = mapped_column(String(40), nullable=False)
    required_capabilities_json: Mapped[list[str]] = mapped_column(
        json_type, nullable=False, default=list
    )


class RunnerRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "runners"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    runner_pool_id: Mapped[str] = mapped_column(
        ForeignKey("runner_pools.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    version: Mapped[str] = mapped_column(String(80), nullable=False)
    capabilities_json: Mapped[list[str]] = mapped_column(json_type, nullable=False, default=list)
    capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
