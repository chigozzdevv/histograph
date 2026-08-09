import asyncio
from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest

from histograph.integrations.datahub.client import (
    DataHubMcpClient,
    DataHubMcpError,
    _require_entity,
)
from histograph.settings import Settings


def test_require_entity_accepts_expected_urn() -> None:
    _require_entity([{"urn": "urn:li:mlModel:fraud"}], "urn:li:mlModel:fraud")


def test_require_entity_surfaces_datahub_lookup_error() -> None:
    with pytest.raises(DataHubMcpError, match="Entity not found"):
        _require_entity(
            [{"urn": "urn:li:mlModel:fraud", "error": "Entity not found"}],
            "urn:li:mlModel:fraud",
        )


def test_health_check_validates_required_mcp_tools(monkeypatch) -> None:
    client = DataHubMcpClient(Settings())

    class FakeSession:
        async def list_tools(self):
            return SimpleNamespace(
                tools=[
                    SimpleNamespace(name="get_lineage"),
                    SimpleNamespace(name="get_entities"),
                ]
            )

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(client, "_session", fake_session)

    result = asyncio.run(client.health_check())

    assert result == {
        "status": "healthy",
        "tools": ["get_entities", "get_lineage"],
    }


def test_health_check_rejects_missing_required_mcp_tool(monkeypatch) -> None:
    client = DataHubMcpClient(Settings())

    class FakeSession:
        async def list_tools(self):
            return SimpleNamespace(tools=[SimpleNamespace(name="get_entities")])

    @asynccontextmanager
    async def fake_session():
        yield FakeSession()

    monkeypatch.setattr(client, "_session", fake_session)

    with pytest.raises(DataHubMcpError, match="get_lineage"):
        asyncio.run(client.health_check())
