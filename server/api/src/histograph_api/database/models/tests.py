from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from histograph_api.database.base import Base
from histograph_api.database.models.common import (
    BaselineStatus,
    SoftDeleteMixin,
    TimestampMixin,
    enum_type,
    json_type,
    new_id,
)


class TestSuiteRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "test_suites"
    __table_args__ = (UniqueConstraint("project_id", "slug"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    slug: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)


class ProtectedQuestionRecord(TimestampMixin, SoftDeleteMixin, Base):
    __tablename__ = "protected_questions"
    __table_args__ = (UniqueConstraint("project_id", "stable_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str] = mapped_column(
        ForeignKey("test_suites.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stable_key: Mapped[str] = mapped_column(String(160), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    criticality: Mapped[str] = mapped_column(String(40), nullable=False, default="medium")
    owner_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    active_version_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "test_versions.id",
            name="fk_protected_questions_active_version_id_test_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    active_baseline_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "baseline_versions.id",
            name="fk_protected_questions_active_baseline_id_baseline_versions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class TestVersionRecord(TimestampMixin, Base):
    __tablename__ = "test_versions"
    __table_args__ = (UniqueConstraint("protected_question_id", "version"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protected_question_id: Mapped[str] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    agent_target_id: Mapped[str] = mapped_column(
        ForeignKey("agent_targets.id", ondelete="RESTRICT"), nullable=False
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    configuration_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class BaselineVersionRecord(TimestampMixin, Base):
    __tablename__ = "baseline_versions"
    __table_args__ = (
        UniqueConstraint("protected_question_id", "version"),
        UniqueConstraint("source_execution_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protected_question_id: Mapped[str] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_version_id: Mapped[str] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT"), nullable=False
    )
    source_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey(
            "test_executions.id",
            name="fk_baseline_versions_source_execution_id_test_executions",
            ondelete="SET NULL",
            use_alter=True,
        ),
        nullable=True,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[BaselineStatus] = mapped_column(
        enum_type(BaselineStatus, "baseline_status"), nullable=False
    )
    evidence_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    assertions_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    environment_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_by: Mapped[str | None] = mapped_column(String(255), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approval_justification: Mapped[str | None] = mapped_column(Text, nullable=True)


class BaselineDependencyRecord(TimestampMixin, Base):
    __tablename__ = "baseline_dependencies"
    __table_args__ = (
        UniqueConstraint("baseline_version_id", "asset_urn", "field_path", "dependency_type"),
        Index("ix_baseline_dependencies_asset", "organization_id", "project_id", "asset_urn"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    baseline_version_id: Mapped[str] = mapped_column(
        ForeignKey("baseline_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_urn: Mapped[str] = mapped_column(String(1024), nullable=False)
    field_path: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    dependency_type: Mapped[str] = mapped_column(String(80), nullable=False)
    environment: Mapped[str] = mapped_column(String(80), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)


class ReviewDecisionRecord(TimestampMixin, Base):
    __tablename__ = "review_decisions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    baseline_version_id: Mapped[str] = mapped_column(
        ForeignKey("baseline_versions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    reviewer_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    decision: Mapped[str] = mapped_column(String(40), nullable=False)
    justification: Mapped[str] = mapped_column(Text, nullable=False)
    before_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
