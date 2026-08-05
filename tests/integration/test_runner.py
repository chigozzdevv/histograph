from histograph_domain import (
    AgentEvent,
    AgentEventType,
    AnalyticsAgentTarget,
    DataHubConnection,
    DataHubContextSnapshot,
    ResponseAssertions,
    ResultAssertions,
    RunRequest,
    RunStatus,
    SqlAssertions,
    TestCase,
)
from histograph_runner import Runner


class DataHubProvider:
    async def verify(self) -> tuple[str, ...]:
        return ("search", "get_entities", "get_lineage")

    async def search_context(
        self,
        question: str,
        context_query: str | None = None,
        limit: int = 10,
    ) -> DataHubContextSnapshot:
        return DataHubContextSnapshot(
            query="/q net+revenue",
            asset_urns=("urn:li:dataset:(urn:li:dataPlatform:postgres,finance.net_revenue,PROD)",),
        )


class Agent:
    async def health(self) -> None:
        return None

    async def invoke(self, question: str, trace_id: str) -> tuple[AgentEvent, ...]:
        return (
            AgentEvent(
                sequence=0,
                type=AgentEventType.SQL,
                trace_id=trace_id,
                payload={
                    "sql": (
                        "SELECT country, SUM(net_revenue) AS net_revenue "
                        "FROM finance.net_revenue GROUP BY country"
                    ),
                    "columns": ["country", "net_revenue"],
                    "rows": [["NG", 140]],
                },
            ),
            AgentEvent(
                sequence=1,
                type=AgentEventType.COMPLETE,
                trace_id=trace_id,
                payload={"text": "Net revenue was $140."},
            ),
        )


async def test_runner_executes_and_evaluates_a_test_case() -> None:
    runner = Runner(
        datahub_factory=lambda _: DataHubProvider(),
        agent_factory=lambda _: Agent(),
    )
    request = RunRequest(
        test_case=TestCase(
            id="net-revenue",
            name="Net revenue",
            question="What was net revenue?",
            sql=SqlAssertions(required_tables=("finance.net_revenue",)),
            result=ResultAssertions(required_columns=("country", "net_revenue"), min_rows=1),
            response=ResponseAssertions(required_phrases=("net revenue",)),
        ),
        datahub=DataHubConnection(mcp_url="http://datahub.test/mcp", token="token"),
        agent=AnalyticsAgentTarget(base_url="http://agent.test", engine_name="warehouse"),
    )

    result = await runner.execute(request, run_id="run-1")

    assert result.run_id == "run-1"
    assert result.status is RunStatus.PASSED
    assert result.evidence.sql_executions[0].columns == ("country", "net_revenue")
