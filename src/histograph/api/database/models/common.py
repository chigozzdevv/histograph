from datetime import datetime
from enum import StrEnum
from uuid import uuid4

from sqlalchemy import JSON, DateTime, Enum, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

json_type = JSON().with_variant(JSONB(), "postgresql")


def new_id() -> str:
    return str(uuid4())


def enum_type(enum: type[StrEnum], name: str) -> Enum:
    return Enum(
        enum,
        name=name,
        validate_strings=True,
        values_callable=lambda members: [member.value for member in members],
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class SoftDeleteMixin:
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Role(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    ENGINEER = "engineer"
    AGENT_OWNER = "agent_owner"
    REVIEWER = "reviewer"
    OBSERVER = "observer"


class ProjectEnvironment(StrEnum):
    DEVELOPMENT = "development"
    STAGING = "staging"
    PRODUCTION = "production"


class ConnectionStatus(StrEnum):
    PENDING = "pending"
    VERIFYING = "verifying"
    READY = "ready"
    DEGRADED = "degraded"
    FAILED = "failed"
    DISABLED = "disabled"


class SecretLocation(StrEnum):
    MANAGED = "managed"
    PRIVATE_RUNNER = "private_runner"


class BaselineStatus(StrEnum):
    DRAFT = "draft"
    APPROVED = "approved"
    SUPERSEDED = "superseded"


class RunStatus(StrEnum):
    QUEUED = "queued"
    PLANNING = "planning"
    ACTION_REQUIRED = "action_required"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    DIAGNOSING = "diagnosing"
    REPORTING = "reporting"
    PASSED = "passed"
    FAILED = "failed"
    WARNING = "warning"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class TriggerType(StrEnum):
    MANUAL = "manual"
    API = "api"
    SCHEDULE = "schedule"
    GITHUB_PULL_REQUEST = "github_pull_request"
    GITHUB_PUSH = "github_push"
    DATAHUB_EVENT = "datahub_event"


class ExecutionStatus(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"
    CANCELLED = "cancelled"
    TIMED_OUT = "timed_out"


class ReceiptStatus(StrEnum):
    RECEIVED = "received"
    PROCESSING = "processing"
    PROCESSED = "processed"
    IGNORED = "ignored"
    FAILED = "failed"


class ScheduleConcurrency(StrEnum):
    SKIP = "skip"
    QUEUE = "queue"
    REPLACE = "replace"


class IncidentStatus(StrEnum):
    OPEN = "open"
    RESOLVED = "resolved"


class ArtifactKind(StrEnum):
    AGENT_TRACE = "agent_trace"
    SQL = "sql"
    RESULT_SAMPLE = "result_sample"
    IMPACT_PLAN = "impact_plan"
    REPORT = "report"
