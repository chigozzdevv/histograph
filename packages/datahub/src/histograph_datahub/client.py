import json
import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import httpx
from histograph_domain import DataHubConnection, DataHubContextSnapshot
from mcp import ClientSession, types
from mcp.client.streamable_http import streamable_http_client

from histograph_datahub.errors import DataHubConnectionError, DataHubToolError

_URN_PATTERN = re.compile(r"urn:li:[A-Za-z0-9_.:-]+(?:\([^\n\r]+?\))?")
_QUERY_STOP_WORDS = {
    "about",
    "after",
    "before",
    "could",
    "from",
    "have",
    "last",
    "month",
    "show",
    "that",
    "their",
    "this",
    "what",
    "when",
    "where",
    "which",
    "with",
    "would",
    "your",
}


class DataHubMcpClient:
    def __init__(self, connection: DataHubConnection):
        self._connection = connection

    @asynccontextmanager
    async def _session(self) -> AsyncIterator[ClientSession]:
        headers = {"Authorization": f"Bearer {self._connection.token.get_secret_value()}"}
        timeout = httpx.Timeout(self._connection.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                headers=headers,
                timeout=timeout,
                follow_redirects=True,
            ) as http_client:
                async with streamable_http_client(
                    str(self._connection.mcp_url),
                    http_client=http_client,
                ) as (read_stream, write_stream, _):
                    async with ClientSession(read_stream, write_stream) as session:
                        await session.initialize()
                        yield session
        except DataHubToolError:
            raise
        except Exception as error:
            raise DataHubConnectionError(f"Unable to connect to DataHub MCP: {error}") from error

    async def list_tools(self) -> tuple[str, ...]:
        async with self._session() as session:
            result = await session.list_tools()
        return tuple(tool.name for tool in result.tools)

    async def verify(self) -> tuple[str, ...]:
        tools = await self.list_tools()
        required = {"search", "get_entities", "get_lineage"}
        missing = sorted(required.difference(tools))
        if missing:
            raise DataHubConnectionError(
                f"DataHub MCP is missing required tools: {', '.join(missing)}"
            )
        return tools

    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any:
        async with self._session() as session:
            result = await session.call_tool(name, arguments=arguments)
        if result.isError:
            message = self._content_text(result.content) or f"DataHub tool {name} failed"
            raise DataHubToolError(message)
        if result.structuredContent is not None:
            return result.structuredContent
        text = self._content_text(result.content)
        if not text:
            return None
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text

    async def search_context(
        self,
        question: str,
        context_query: str | None = None,
        limit: int = 10,
    ) -> DataHubContextSnapshot:
        query = self._build_query(context_query or question)
        search_result = await self.call_tool(
            "search",
            {"query": query, "num_results": limit},
        )
        urns = self._extract_urns(search_result)
        entities: tuple[dict[str, Any], ...] = ()
        if urns:
            entity_result = await self.call_tool("get_entities", {"urns": list(urns[:5])})
            if isinstance(entity_result, dict):
                entities = (entity_result,)
            elif isinstance(entity_result, list):
                entities = tuple(item for item in entity_result if isinstance(item, dict))
        return DataHubContextSnapshot(query=query, asset_urns=urns, entities=entities)

    async def get_downstream_lineage(
        self,
        urn: str,
        *,
        max_hops: int = 3,
        max_results: int = 100,
    ) -> tuple[dict[str, Any], ...]:
        results: list[dict[str, Any]] = []
        offset = 0
        while True:
            response = await self.call_tool(
                "get_lineage",
                {
                    "urn": urn,
                    "upstream": False,
                    "max_hops": max_hops,
                    "max_results": max_results,
                    "offset": offset,
                },
            )
            direction = response.get("downstreams", {}) if isinstance(response, dict) else {}
            page = direction.get("searchResults", []) if isinstance(direction, dict) else []
            results.extend(item for item in page if isinstance(item, dict))
            returned = int(direction.get("returned", len(page)))
            if not direction.get("hasMore") or returned == 0:
                break
            offset += returned
        return tuple(results)

    @staticmethod
    def _content_text(content: list[types.ContentBlock]) -> str:
        return "\n".join(block.text for block in content if isinstance(block, types.TextContent))

    @staticmethod
    def _build_query(value: str) -> str:
        stripped = value.strip()
        if stripped == "*" or stripped.startswith("/q "):
            return stripped
        terms = [
            term
            for term in re.findall(r"[A-Za-z][A-Za-z0-9_]+", stripped.lower())
            if len(term) > 2 and term not in _QUERY_STOP_WORDS
        ]
        unique_terms = tuple(dict.fromkeys(terms))[:6]
        return f"/q {'+'.join(unique_terms)}" if unique_terms else "*"

    @classmethod
    def _extract_urns(cls, value: Any) -> tuple[str, ...]:
        found: list[str] = []

        def visit(item: Any) -> None:
            if isinstance(item, dict):
                urn = item.get("urn")
                if isinstance(urn, str) and urn.startswith("urn:li:"):
                    found.append(urn)
                for child in item.values():
                    visit(child)
            elif isinstance(item, list):
                for child in item:
                    visit(child)
            elif isinstance(item, str):
                found.extend(_URN_PATTERN.findall(item))

        visit(value)
        return tuple(dict.fromkeys(found))
