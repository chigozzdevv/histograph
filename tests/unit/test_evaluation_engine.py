from histograph.domain import (
    AgentEvent,
    AgentEventType,
    AssetAssertions,
    DataHubContextSnapshot,
    EvaluationStatus,
    ExecutionEvidence,
    ResponseAssertions,
    ResultAssertions,
    SqlAssertions,
    SqlExecution,
    TestCase,
)
from histograph.evaluation import EvaluationEngine

NET_REVENUE_URN = "urn:li:dataset:(urn:li:dataPlatform:postgres,finance.net_revenue,PROD)"


def test_evaluator_accepts_semantically_valid_execution() -> None:
    test_case = TestCase(
        id="net-revenue",
        name="Net revenue by country",
        question="What was net revenue by country last month?",
        assets=AssetAssertions(required=(NET_REVENUE_URN,)),
        sql=SqlAssertions(
            dialect="postgres",
            required_tables=("finance.net_revenue",),
            required_columns=("country", "net_revenue"),
        ),
        result=ResultAssertions(
            required_columns=("country", "net_revenue"),
            min_rows=1,
            max_null_fraction={"country": 0},
        ),
        response=ResponseAssertions(required_phrases=("net revenue",)),
    )
    evidence = ExecutionEvidence(
        context=DataHubContextSnapshot(query="/q net+revenue"),
        events=(
            AgentEvent(
                sequence=0,
                type=AgentEventType.COMPLETE,
                trace_id="run-1",
                payload={"text": "Net revenue was $140 by country."},
            ),
        ),
        selected_asset_urns=(NET_REVENUE_URN,),
        sql_executions=(
            SqlExecution(
                sql=(
                    "SELECT country, SUM(net_revenue) AS net_revenue "
                    "FROM finance.net_revenue GROUP BY country"
                ),
                columns=("country", "net_revenue"),
                rows=(("NG", 140),),
            ),
        ),
        final_response="Net revenue was $140 by country.",
    )

    report = EvaluationEngine().evaluate(test_case, evidence)

    assert report.status is EvaluationStatus.PASSED
    assert all(finding.passed for finding in report.findings)


def test_evaluator_rejects_missing_required_table() -> None:
    test_case = TestCase(
        id="net-revenue",
        name="Net revenue",
        question="What was net revenue?",
        sql=SqlAssertions(required_tables=("refunds",)),
    )
    evidence = ExecutionEvidence(
        context=DataHubContextSnapshot(query="/q net+revenue"),
        events=(),
        sql_executions=(
            SqlExecution(
                sql="SELECT SUM(total) AS revenue FROM orders",
                columns=("revenue",),
                rows=((200,),),
            ),
        ),
        final_response="Revenue was $200.",
    )

    report = EvaluationEngine().evaluate(test_case, evidence)

    assert report.status is EvaluationStatus.FAILED
    assert any(
        finding.code == "sql.table-required" and not finding.passed for finding in report.findings
    )
