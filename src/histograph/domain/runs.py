from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from pydantic import Field

from histograph.domain.base import DomainModel
from histograph.domain.cases import TestCase
from histograph.domain.evaluation import EvaluationReport
from histograph.domain.evidence import ExecutionEvidence
from histograph.domain.targets import AnalyticsAgentTarget, DataHubConnection


class RunStatus(StrEnum):
    QUEUED = "queued"
    EXECUTING = "executing"
    EVALUATING = "evaluating"
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class RunRequest(DomainModel):
    test_case: TestCase
    datahub: DataHubConnection
    agent: AnalyticsAgentTarget


class RunResult(DomainModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    status: RunStatus
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime
    evidence: ExecutionEvidence
    evaluation: EvaluationReport
