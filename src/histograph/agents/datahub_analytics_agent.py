import json
from typing import Any
from uuid import uuid4

import httpx

from histograph.agents.errors import AgentConnectionError, AgentProtocolError
from histograph.agents.sse import iter_sse_data
from histograph.domain import AgentEvent, AgentEventType, AnalyticsAgentTarget

_EVENT_TYPES = {
    "TEXT": AgentEventType.TEXT,
    "TOOL_CALL": AgentEventType.TOOL_CALL,
    "TOOL_RESULT": AgentEventType.TOOL_RESULT,
    "SQL": AgentEventType.SQL,
    "RESULT": AgentEventType.RESULT,
    "CHART": AgentEventType.CHART,
    "USAGE": AgentEventType.USAGE,
    "ERROR": AgentEventType.ERROR,
    "COMPLETE": AgentEventType.COMPLETE,
}


class DataHubAnalyticsAgentAdapter:
    def __init__(
        self,
        target: AnalyticsAgentTarget,
        client: httpx.AsyncClient | None = None,
    ):
        self._target = target
        self._client = client

    async def health(self) -> None:
        try:
            response = await self._request("GET", "/health")
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise AgentConnectionError(f"Analytics Agent health check failed: {error}") from error
        if payload.get("status") != "ok":
            raise AgentConnectionError("Analytics Agent returned an unhealthy status")

    async def invoke(self, question: str, trace_id: str) -> tuple[AgentEvent, ...]:
        conversation_id = await self._create_conversation(trace_id)
        events: list[AgentEvent] = []
        completed = False
        client, owns_client = self._get_client()
        try:
            async with client.stream(
                "POST",
                self._url(f"/api/conversations/{conversation_id}/messages"),
                headers=self._headers(),
                json={"text": question},
            ) as response:
                response.raise_for_status()
                async for raw_data in iter_sse_data(response):
                    event = self._normalize_event(raw_data, len(events), trace_id)
                    if event is None:
                        continue
                    events.append(event)
                    completed = completed or event.type is AgentEventType.COMPLETE
        except httpx.HTTPStatusError as error:
            detail = error.response.text[:500]
            raise AgentConnectionError(
                f"Analytics Agent invocation failed with {error.response.status_code}: {detail}"
            ) from error
        except AgentProtocolError:
            raise
        except Exception as error:
            raise AgentConnectionError(f"Analytics Agent invocation failed: {error}") from error
        finally:
            if owns_client:
                await client.aclose()
        if not completed:
            raise AgentProtocolError("Analytics Agent stream ended without a COMPLETE event")
        return tuple(events)

    async def _create_conversation(self, trace_id: str) -> str:
        try:
            response = await self._request(
                "POST",
                "/api/conversations",
                json={
                    "title": f"Histograph run {trace_id[:8]}",
                    "engine_name": self._target.engine_name,
                },
            )
            response.raise_for_status()
            payload = response.json()
        except Exception as error:
            raise AgentConnectionError(
                f"Unable to create Analytics Agent conversation: {error}"
            ) from error
        conversation_id = payload.get("id")
        if not isinstance(conversation_id, str) or not conversation_id:
            raise AgentProtocolError("Analytics Agent conversation response did not contain an id")
        return conversation_id

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        client, owns_client = self._get_client()
        try:
            return await client.request(
                method,
                self._url(path),
                headers=self._headers(),
                **kwargs,
            )
        finally:
            if owns_client:
                await client.aclose()

    def _get_client(self) -> tuple[httpx.AsyncClient, bool]:
        if self._client is not None:
            return self._client, False
        timeout = httpx.Timeout(self._target.timeout_seconds)
        return httpx.AsyncClient(timeout=timeout, follow_redirects=True), True

    def _headers(self) -> dict[str, str]:
        if self._target.token is None:
            return {}
        return {"Authorization": f"Bearer {self._target.token.get_secret_value()}"}

    def _url(self, path: str) -> str:
        return f"{str(self._target.base_url).rstrip('/')}{path}"

    @staticmethod
    def _normalize_event(raw_data: str, sequence: int, trace_id: str) -> AgentEvent | None:
        try:
            data = json.loads(raw_data)
        except json.JSONDecodeError as error:
            raise AgentProtocolError(
                f"Analytics Agent emitted invalid JSON: {raw_data[:200]}"
            ) from error
        event_name = str(data.get("event", "")).upper()
        if event_name == "KEEPALIVE":
            return None
        event_type = _EVENT_TYPES.get(event_name)
        if event_type is None:
            raise AgentProtocolError(f"Analytics Agent emitted an unknown event: {event_name}")
        payload = data.get("payload", {})
        if not isinstance(payload, dict):
            raise AgentProtocolError(f"Analytics Agent {event_name} payload must be an object")
        event_id = data.get("message_id")
        return AgentEvent(
            event_id=event_id if isinstance(event_id, str) and event_id else str(uuid4()),
            sequence=sequence,
            type=event_type,
            payload=payload,
            trace_id=trace_id,
        )
