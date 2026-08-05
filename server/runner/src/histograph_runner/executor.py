import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol
from uuid import uuid4

from histograph_agents import AgentAdapter, DataHubAnalyticsAgentAdapter
from histograph_datahub import DataHubMcpClient
from histograph_domain import (
    AnalyticsAgentTarget,
    DataHubConnection,
    DataHubContextSnapshot,
    EvaluationStatus,
    RunRequest,
    RunResult,
    RunStatus,
)
from histograph_evaluation import EvaluationEngine

from histograph_runner.errors import RunExecutionError
from histograph_runner.evidence import build_evidence


class DataHubContextProvider(Protocol):
    async def verify(self) -> tuple[str, ...]: ...

    async def search_context(
        self,
        question: str,
        context_query: str | None = None,
        limit: int = 10,
    ) -> DataHubContextSnapshot: ...


class Runner:
    def __init__(
        self,
        datahub_factory: Callable[[DataHubConnection], DataHubContextProvider] = DataHubMcpClient,
        agent_factory: Callable[
            [AnalyticsAgentTarget], AgentAdapter
        ] = DataHubAnalyticsAgentAdapter,
        evaluator: EvaluationEngine | None = None,
    ):
        self._datahub_factory = datahub_factory
        self._agent_factory = agent_factory
        self._evaluator = evaluator or EvaluationEngine()

    async def execute(self, request: RunRequest, run_id: str | None = None) -> RunResult:
        identifier = run_id or str(uuid4())
        started_at = datetime.now(UTC)
        datahub = self._datahub_factory(request.datahub)
        agent = self._agent_factory(request.agent)
        try:
            async with asyncio.TaskGroup() as group:
                group.create_task(datahub.verify())
                group.create_task(agent.health())
            context = await datahub.search_context(
                request.test_case.question,
                request.test_case.context_query,
            )
            events = await agent.invoke(request.test_case.question, identifier)
        except ExceptionGroup as error:
            cause = error.exceptions[0] if error.exceptions else error
            raise RunExecutionError(str(cause)) from cause
        except Exception as error:
            raise RunExecutionError(str(error)) from error
        evidence = build_evidence(context, events)
        evaluation = self._evaluator.evaluate(request.test_case, evidence)
        status = (
            RunStatus.PASSED if evaluation.status is EvaluationStatus.PASSED else RunStatus.FAILED
        )
        return RunResult(
            run_id=identifier,
            status=status,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            evidence=evidence,
            evaluation=evaluation,
        )
