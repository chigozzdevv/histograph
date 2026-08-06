import json

import httpx

from histograph.agents import DataHubAnalyticsAgentAdapter
from histograph.domain import AgentEventType, AnalyticsAgentTarget


async def test_adapter_consumes_real_analytics_agent_sse_shape() -> None:
    events = [
        {
            "event": "TOOL_CALL",
            "conversation_id": "conversation-1",
            "message_id": "message-1",
            "payload": {"tool_name": "search", "tool_input": {"query": "/q revenue"}},
        },
        {
            "event": "SQL",
            "conversation_id": "conversation-1",
            "message_id": "message-2",
            "payload": {
                "sql": "SELECT country, SUM(net_revenue) FROM finance.net_revenue GROUP BY 1",
                "columns": ["country", "net_revenue"],
                "rows": [["NG", 140]],
                "truncated": False,
            },
        },
        {
            "event": "COMPLETE",
            "conversation_id": "conversation-1",
            "message_id": "message-3",
            "payload": {"text": "Net revenue was $140."},
        },
    ]
    sse = "".join(f"data: {json.dumps(event)}\n\n" for event in events)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/health":
            return httpx.Response(200, json={"status": "ok"})
        if request.url.path == "/api/conversations":
            return httpx.Response(201, json={"id": "conversation-1"})
        if request.url.path == "/api/conversations/conversation-1/messages":
            return httpx.Response(200, text=sse, headers={"content-type": "text/event-stream"})
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = DataHubAnalyticsAgentAdapter(
            AnalyticsAgentTarget(base_url="http://agent.test", engine_name="warehouse"),
            client=client,
        )
        await adapter.health()
        result = await adapter.invoke("What was net revenue?", "run-1")

    assert [event.type for event in result] == [
        AgentEventType.TOOL_CALL,
        AgentEventType.SQL,
        AgentEventType.COMPLETE,
    ]
    assert result[1].payload["rows"] == [["NG", 140]]
