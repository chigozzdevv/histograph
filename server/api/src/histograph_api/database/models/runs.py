from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from histograph_api.database.base import Base
from histograph_api.database.models.common import (
    ArtifactKind,
    ExecutionStatus,
    RunStatus,
    TimestampMixin,
    TriggerType,
    enum_type,
    json_type,
    new_id,
)


class RunRecord(TimestampMixin, Base):
    __tablename__ = "runs"
    __table_args__ = (
        UniqueConstraint("organization_id", "project_id", "idempotency_key"),
        Index("ix_runs_project_status_created", "project_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    trigger_type: Mapped[TriggerType] = mapped_column(
        enum_type(TriggerType, "run_trigger_type"), nullable=False
    )
    trigger_reference: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[RunStatus] = mapped_column(enum_type(RunStatus, "run_status"), nullable=False)
    workflow_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True)
    configuration_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    selection_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
    impact_plan_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    report_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    queued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    planned_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancellation_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )


class ImpactPlanRecord(TimestampMixin, Base):
    __tablename__ = "impact_plans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    risk_level: Mapped[str] = mapped_column(String(40), nullable=False)
    plan_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    selection_policy_version: Mapped[str] = mapped_column(String(80), nullable=False)


class RunTestSelectionRecord(TimestampMixin, Base):
    __tablename__ = "run_test_selections"
    __table_args__ = (UniqueConstraint("run_id", "protected_question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protected_question_id: Mapped[str] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="CASCADE"), nullable=False
    )
    selected: Mapped[bool] = mapped_column(Boolean, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)


class TestExecutionRecord(TimestampMixin, Base):
    __tablename__ = "test_executions"
    __table_args__ = (UniqueConstraint("run_id", "protected_question_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protected_question_id: Mapped[str] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="RESTRICT"), nullable=False
    )
    test_version_id: Mapped[str] = mapped_column(
        ForeignKey("test_versions.id", ondelete="RESTRICT"), nullable=False
    )
    baseline_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("baseline_versions.id", ondelete="RESTRICT"), nullable=True
    )
    agent_target_id: Mapped[str] = mapped_column(
        ForeignKey("agent_targets.id", ondelete="RESTRICT"), nullable=False
    )
    status: Mapped[ExecutionStatus] = mapped_column(
        enum_type(ExecutionStatus, "test_execution_status"), nullable=False
    )
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    evaluation_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ExecutionAttemptRecord(TimestampMixin, Base):
    __tablename__ = "execution_attempts"
    __table_args__ = (UniqueConstraint("test_execution_id", "attempt_number"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    test_execution_id: Mapped[str] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[ExecutionStatus] = mapped_column(
        enum_type(ExecutionStatus, "execution_attempt_status"), nullable=False
    )
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(120), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class AgentEventRecord(TimestampMixin, Base):
    __tablename__ = "agent_events"
    __table_args__ = (
        UniqueConstraint(
            "test_execution_id", "sequence", name="uq_agent_events_execution_sequence"
        ),
        UniqueConstraint(
            "test_execution_id", "event_id", name="uq_agent_events_execution_event_id"
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    test_execution_id: Mapped[str] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    event_id: Mapped[str] = mapped_column(String(64), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    trace_id: Mapped[str] = mapped_column(String(64), nullable=False)
    event_timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    payload_json: Mapped[dict] = mapped_column(json_type, nullable=False)


class ArtifactReferenceRecord(TimestampMixin, Base):
    __tablename__ = "artifact_references"
    __table_args__ = (UniqueConstraint("organization_id", "object_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_execution_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=True
    )
    kind: Mapped[ArtifactKind] = mapped_column(
        enum_type(ArtifactKind, "artifact_kind"), nullable=False
    )
    object_key: Mapped[str] = mapped_column(String(1024), nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
