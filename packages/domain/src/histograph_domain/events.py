from datetime import UTC, datetime
from enum import StrEnum
from typing import Any
from uuid import uuid4

from pydantic import Field

from histograph_domain.base import DomainModel


class AgentEventType(StrEnum):
    TEXT = "text"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    SQL = "sql"
    RESULT = "result"
    CHART = "chart"
    USAGE = "usage"
    ERROR = "error"
    COMPLETE = "complete"


class AgentEvent(DomainModel):
    event_id: str = Field(default_factory=lambda: str(uuid4()))
    sequence: int = Field(ge=0)
    timestamp: datetime = Field(default_factory=lambda: datetime.now(UTC))
    type: AgentEventType
    payload: dict[str, Any] = Field(default_factory=dict)
    trace_id: str
