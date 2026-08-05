import re
from typing import Any

from histograph_domain import (
    AgentEvent,
    AgentEventType,
    DataHubContextSnapshot,
    ExecutionEvidence,
    SqlExecution,
)

_URN_PATTERN = re.compile(r"urn:li:[A-Za-z0-9_.:-]+(?:\([^\n\r]+?\))?")


def build_evidence(
    context: DataHubContextSnapshot,
    events: tuple[AgentEvent, ...],
) -> ExecutionEvidence:
    selected_assets: list[str] = []
    executions: list[SqlExecution] = []
    errors: list[str] = []
    final_response = ""
    for event in events:
        if event.type in {AgentEventType.TOOL_CALL, AgentEventType.TOOL_RESULT}:
            selected_assets.extend(_extract_urns(event.payload))
        if event.type is AgentEventType.SQL:
            executions.append(
                SqlExecution(
                    sql=str(event.payload.get("sql", "")),
                    columns=tuple(str(column) for column in event.payload.get("columns", [])),
                    rows=tuple(event.payload.get("rows", [])),
                    truncated=bool(event.payload.get("truncated", False)),
                )
            )
        if event.type is AgentEventType.ERROR:
            errors.append(str(event.payload.get("error", "Agent execution failed")))
        if event.type is AgentEventType.TOOL_RESULT and event.payload.get("is_error"):
            tool_name = event.payload.get("tool_name", "unknown tool")
            errors.append(f"{tool_name}: {event.payload.get('result', 'tool failed')}")
        if event.type is AgentEventType.COMPLETE:
            final_response = str(event.payload.get("text", ""))
    return ExecutionEvidence(
        context=context,
        events=events,
        selected_asset_urns=tuple(dict.fromkeys(selected_assets)),
        sql_executions=tuple(executions),
        final_response=final_response,
        errors=tuple(errors),
    )


def _extract_urns(value: Any) -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for item in value.values():
            found.extend(_extract_urns(item))
    elif isinstance(value, list):
        for item in value:
            found.extend(_extract_urns(item))
    elif isinstance(value, str):
        found.extend(_URN_PATTERN.findall(value))
    return found
