import asyncio
import json
import os
from collections.abc import AsyncIterator, Mapping
from contextlib import asynccontextmanager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from histograph.settings import Settings


class DataHubMcpError(RuntimeError):
    """Raised when the DataHub MCP server cannot complete a request."""


class DataHubMcpClient:
    def __init__(self, settings: Settings):
        self._settings = settings

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        environment = os.environ.copy()
        environment["DATAHUB_GMS_URL"] = self._settings.datahub_gms_url
        if self._settings.datahub_gms_token:
            environment["DATAHUB_GMS_TOKEN"] = self._settings.datahub_gms_token

        parameters = StdioServerParameters(
            command=self._settings.datahub_mcp_command,
            args=[self._settings.datahub_mcp_package],
            env=environment,
        )
        try:
            async with stdio_client(parameters) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    yield session
        except Exception as error:
            raise DataHubMcpError(f"DataHub MCP connection failed: {error}") from error

    async def _call(
        self, session: ClientSession, tool: str, arguments: Mapping[str, Any]
    ) -> Any:
        try:
            result = await session.call_tool(tool, arguments=dict(arguments))
        except Exception as error:
            raise DataHubMcpError(f"DataHub MCP tool {tool} failed: {error}") from error
        if result.isError:
            raise DataHubMcpError(f"DataHub MCP tool {tool} returned an error: {_text(result)}")
        return _payload(result)

    async def collect_context(self, model_urn: str, max_hops: int = 3) -> dict[str, Any]:
        async def collect() -> dict[str, Any]:
            async with self._session() as session:
                model = await self._call(session, "get_entities", {"urns": [model_urn]})
                upstream = await self._call(
                    session,
                    "get_lineage",
                    {"urn": model_urn, "upstream": True, "max_hops": max_hops, "max_results": 100},
                )
                downstream = await self._call(
                    session,
                    "get_lineage",
                    {
                        "urn": model_urn,
                        "upstream": False,
                        "max_hops": max_hops,
                        "max_results": 100,
                    },
                )
                related_urns = _lineage_urns(upstream) | _lineage_urns(downstream)
                related_entities = []
                if related_urns:
                    related_entities = await self._call(
                        session, "get_entities", {"urns": sorted(related_urns)}
                    )
                return {
                    "model": model,
                    "upstream": upstream,
                    "downstream": downstream,
                    "related_entities": related_entities,
                    "tool_trace": ["get_entities", "get_lineage:upstream", "get_lineage:downstream"]
                    + (["get_entities:lineage_assets"] if related_urns else []),
                }

        try:
            return await asyncio.wait_for(
                collect(), timeout=self._settings.datahub_mcp_timeout_seconds
            )
        except TimeoutError as error:
            raise DataHubMcpError("DataHub MCP investigation timed out") from error

    async def save_investigation(
        self,
        title: str,
        content: str,
        related_assets: list[str],
    ) -> dict[str, Any]:
        if not self._settings.datahub_mcp_mutations_enabled:
            raise DataHubMcpError("DataHub MCP mutations are disabled")

        async def save() -> dict[str, Any]:
            async with self._session() as session:
                result = await self._call(
                    session,
                    "save_document",
                    {
                        "document_type": "Analysis",
                        "title": title,
                        "content": content,
                        "topics": ["histograph", "ml-incident", "lineage"],
                        "related_assets": related_assets,
                    },
                )
                return result if isinstance(result, dict) else {"result": result}

        try:
            return await asyncio.wait_for(
                save(), timeout=self._settings.datahub_mcp_timeout_seconds
            )
        except TimeoutError as error:
            raise DataHubMcpError("DataHub MCP write-back timed out") from error


def _payload(result: Any) -> Any:
    structured = getattr(result, "structuredContent", None)
    if structured is None:
        structured = getattr(result, "structured_content", None)
    if structured is not None:
        return structured

    texts = _text_parts(result)
    if len(texts) == 1:
        try:
            return json.loads(texts[0])
        except json.JSONDecodeError:
            return {"text": texts[0]}
    return {"content": texts}


def _text(result: Any) -> str:
    return "\n".join(_text_parts(result)) or "unknown error"


def _text_parts(result: Any) -> list[str]:
    parts: list[str] = []
    for content in getattr(result, "content", []) or []:
        if getattr(content, "type", None) == "text":
            parts.append(content.text)
    return parts


def _lineage_urns(payload: Any) -> set[str]:
    urns: set[str] = set()
    if not isinstance(payload, Mapping):
        return urns
    for direction in ("upstreams", "downstreams"):
        direction_payload = payload.get(direction)
        if not isinstance(direction_payload, Mapping):
            continue
        for result in direction_payload.get("searchResults", []) or []:
            if not isinstance(result, Mapping):
                continue
            entity = result.get("entity")
            if isinstance(entity, Mapping) and isinstance(entity.get("urn"), str):
                urns.add(entity["urn"])
    return urns
