from typing import Any

from histograph_domain.base import DomainModel
from histograph_domain.events import AgentEvent


class DataHubContextSnapshot(DomainModel):
    query: str
    asset_urns: tuple[str, ...] = ()
    entities: tuple[dict[str, Any], ...] = ()


class SqlExecution(DomainModel):
    sql: str
    columns: tuple[str, ...] = ()
    rows: tuple[Any, ...] = ()
    truncated: bool = False


class ExecutionEvidence(DomainModel):
    context: DataHubContextSnapshot
    events: tuple[AgentEvent, ...]
    selected_asset_urns: tuple[str, ...] = ()
    sql_executions: tuple[SqlExecution, ...] = ()
    final_response: str = ""
    errors: tuple[str, ...] = ()
