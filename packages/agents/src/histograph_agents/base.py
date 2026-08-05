from typing import Protocol

from histograph_domain import AgentEvent


class AgentAdapter(Protocol):
    async def health(self) -> None: ...

    async def invoke(self, question: str, trace_id: str) -> tuple[AgentEvent, ...]: ...
