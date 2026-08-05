from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from histograph_api.database.base import Base
from histograph_api.database.models.common import (
    IncidentStatus,
    ReceiptStatus,
    ScheduleConcurrency,
    TimestampMixin,
    enum_type,
    json_type,
    new_id,
)


class ScheduleRecord(TimestampMixin, Base):
    __tablename__ = "schedules"
    __table_args__ = (UniqueConstraint("project_id", "name"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    suite_id: Mapped[str | None] = mapped_column(
        ForeignKey("test_suites.id", ondelete="CASCADE"), nullable=True
    )
    protected_question_id: Mapped[str | None] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="CASCADE"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    cron_expression: Mapped[str] = mapped_column(String(160), nullable=False)
    timezone: Mapped[str] = mapped_column(String(80), nullable=False)
    concurrency_policy: Mapped[ScheduleConcurrency] = mapped_column(
        enum_type(ScheduleConcurrency, "schedule_concurrency"), nullable=False
    )
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    temporal_schedule_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    created_by: Mapped[str] = mapped_column(String(255), nullable=False)


class MetadataEventReceiptRecord(TimestampMixin, Base):
    __tablename__ = "metadata_event_receipts"
    __table_args__ = (
        UniqueConstraint("organization_id", "source", "idempotency_key"),
        Index("ix_metadata_events_project_status", "project_id", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    datahub_connection_id: Mapped[str] = mapped_column(
        ForeignKey("datahub_connections.id", ondelete="CASCADE"), nullable=False
    )
    source: Mapped[str] = mapped_column(String(120), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(512), nullable=False)
    entity_urn: Mapped[str] = mapped_column(String(1024), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    aspect_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    aspect_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    payload_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    status: Mapped[ReceiptStatus] = mapped_column(
        enum_type(ReceiptStatus, "metadata_receipt_status"), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class WebhookReceiptRecord(TimestampMixin, Base):
    __tablename__ = "webhook_receipts"
    __table_args__ = (UniqueConstraint("source", "delivery_id"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str | None] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    source: Mapped[str] = mapped_column(String(80), nullable=False)
    delivery_id: Mapped[str] = mapped_column(String(255), nullable=False)
    event_type: Mapped[str] = mapped_column(String(160), nullable=False)
    action: Mapped[str | None] = mapped_column(String(160), nullable=True)
    signature_valid: Mapped[bool] = mapped_column(Boolean, nullable=False)
    payload_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    status: Mapped[ReceiptStatus] = mapped_column(
        enum_type(ReceiptStatus, "webhook_receipt_status"), nullable=False
    )
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("runs.id", ondelete="SET NULL"), nullable=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class IncidentRecord(TimestampMixin, Base):
    __tablename__ = "incidents"
    __table_args__ = (UniqueConstraint("organization_id", "project_id", "fingerprint"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    protected_question_id: Mapped[str] = mapped_column(
        ForeignKey("protected_questions.id", ondelete="CASCADE"), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[IncidentStatus] = mapped_column(
        enum_type(IncidentStatus, "incident_status"), nullable=False
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    resource_urn: Mapped[str] = mapped_column(String(1024), nullable=False)
    first_run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False
    )
    latest_run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="RESTRICT"), nullable=False
    )
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    consecutive_success_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    datahub_incident_urn: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class IncidentOccurrenceRecord(TimestampMixin, Base):
    __tablename__ = "incident_occurrences"
    __table_args__ = (
        UniqueConstraint("incident_id", "run_id", "test_execution_id", "occurrence_type"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[str] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=False, index=True
    )
    run_id: Mapped[str] = mapped_column(
        ForeignKey("runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    test_execution_id: Mapped[str] = mapped_column(
        ForeignKey("test_executions.id", ondelete="CASCADE"), nullable=False
    )
    occurrence_type: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)


class DataHubWritebackRecord(TimestampMixin, Base):
    __tablename__ = "datahub_writebacks"
    __table_args__ = (UniqueConstraint("organization_id", "idempotency_key"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    incident_id: Mapped[str | None] = mapped_column(
        ForeignKey("incidents.id", ondelete="CASCADE"), nullable=True
    )
    run_id: Mapped[str] = mapped_column(ForeignKey("runs.id", ondelete="CASCADE"), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False)
    operation: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    request_json: Mapped[dict] = mapped_column(json_type, nullable=False)
    response_json: Mapped[dict | None] = mapped_column(json_type, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)


class AuditEventRecord(TimestampMixin, Base):
    __tablename__ = "audit_events"
    __table_args__ = (
        Index("ix_audit_events_scope_created", "organization_id", "project_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    organization_id: Mapped[str] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), nullable=True, index=True
    )
    actor_type: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_id: Mapped[str] = mapped_column(String(255), nullable=False)
    action: Mapped[str] = mapped_column(String(160), nullable=False)
    target_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
    before_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    after_fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    details_json: Mapped[dict] = mapped_column(json_type, nullable=False, default=dict)
