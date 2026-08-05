import sqlite3

from fastapi.testclient import TestClient
from histograph_api.config import Settings
from histograph_api.main import create_app
from histograph_domain import (
    AgentEvent,
    AgentEventType,
    DataHubContextSnapshot,
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
        return DataHubContextSnapshot(query="/q revenue")


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
                    "sql": "SELECT SUM(net_revenue) AS net_revenue FROM finance.net_revenue",
                    "columns": ["net_revenue"],
                    "rows": [[140]],
                },
            ),
            AgentEvent(
                sequence=1,
                type=AgentEventType.COMPLETE,
                trace_id=trace_id,
                payload={"text": "Net revenue was $140."},
            ),
        )


def test_api_executes_and_persists_a_run_without_secrets(tmp_path) -> None:
    database_path = tmp_path / "histograph.db"
    settings = Settings(database_url=f"sqlite+aiosqlite:///{database_path}")
    runner = Runner(
        datahub_factory=lambda _: DataHubProvider(),
        agent_factory=lambda _: Agent(),
    )
    app = create_app(settings=settings, runner=runner)
    payload = {
        "test_case": {
            "id": "net-revenue",
            "name": "Net revenue",
            "question": "What was net revenue?",
            "sql": {"required_tables": ["finance.net_revenue"]},
            "result": {"required_columns": ["net_revenue"], "min_rows": 1},
            "response": {"required_phrases": ["net revenue"]},
        },
        "datahub": {
            "mcp_url": "http://datahub.test/mcp",
            "token": "datahub-secret",
        },
        "agent": {
            "base_url": "http://agent.test",
            "engine_name": "warehouse",
            "token": "agent-secret",
        },
    }

    with TestClient(app) as client:
        preflight = client.options(
            "/v1/runs",
            headers={
                "Origin": "http://127.0.0.1:3000",
                "Access-Control-Request-Method": "POST",
            },
        )
        assert preflight.status_code == 200
        assert preflight.headers["access-control-allow-origin"] == "http://127.0.0.1:3000"

        response = client.post("/v1/runs", json=payload)
        assert response.status_code == 201
        run = response.json()
        assert run["status"] == "passed"
        listed = client.get("/v1/runs").json()["items"]
        assert [item["id"] for item in listed] == [run["id"]]

    connection = sqlite3.connect(database_path)
    stored_request = connection.execute("SELECT request_json FROM runs").fetchone()[0]
    connection.close()
    assert "datahub-secret" not in stored_request
    assert "agent-secret" not in stored_request
