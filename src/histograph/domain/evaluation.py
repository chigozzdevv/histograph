from enum import StrEnum
from typing import Any

from pydantic import Field

from histograph.domain.base import DomainModel


class EvaluationStatus(StrEnum):
    PASSED = "passed"
    FAILED = "failed"
    ERROR = "error"


class FindingLevel(StrEnum):
    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class EvaluationFinding(DomainModel):
    code: str
    message: str
    passed: bool
    level: FindingLevel
    evidence: dict[str, Any] = Field(default_factory=dict)


class EvaluationReport(DomainModel):
    status: EvaluationStatus
    findings: tuple[EvaluationFinding, ...]
