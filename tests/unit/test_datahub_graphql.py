import json

import httpx
import pytest

from histograph.datahub import DataHubGraphqlClient, DataHubGraphqlError


@pytest.mark.asyncio
async def test_datahub_graphql_incident_lifecycle() -> None:
    requests: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url == "https://datahub.example/api/graphql"
        assert request.headers["Authorization"] == "Bearer datahub-token"
        payload = json.loads(request.content)
        requests.append(payload)
        query = payload["query"]
        if "HistographVerifyDataHub" in query:
            return httpx.Response(
                200,
                json={"data": {"me": {"corpUser": {"urn": "urn:li:corpuser:histograph"}}}},
            )
        if "HistographActiveIncidents" in query:
            return httpx.Response(
                200,
                json={
                    "data": {
                        "dataset": {
                            "incidents": {
                                "incidents": [
                                    {
                                        "urn": "urn:li:incident:existing",
                                        "title": "Agent regression",
                                        "description": "Ownership marker: histograph:incident-1",
                                    }
                                ]
                            }
                        }
                    }
                },
            )
        if "HistographRaiseIncident" in query:
            return httpx.Response(
                200,
                json={"data": {"raiseIncident": "urn:li:incident:created"}},
            )
        if "HistographUpdateIncident" in query:
            return httpx.Response(200, json={"data": {"updateIncident": "urn:li:incident:created"}})
        if "HistographResolveIncident" in query:
            return httpx.Response(200, json={"data": {"updateIncidentStatus": True}})
        raise AssertionError(f"Unexpected DataHub GraphQL query: {query}")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DataHubGraphqlClient(
        endpoint_url="https://datahub.example/",
        token="datahub-token",
        http_client=http_client,
    )
    try:
        assert await client.verify() == "urn:li:corpuser:histograph"
        assert (
            await client.find_owned_active_incident(
                resource_urn="urn:li:dataset:(snowflake,revenue,PROD)",
                ownership_marker="histograph:incident-1",
            )
            == "urn:li:incident:existing"
        )
        assert (
            await client.raise_incident(
                resource_urn="urn:li:dataset:(snowflake,revenue,PROD)",
                title="Agent regression",
                description="Histograph evidence",
            )
            == "urn:li:incident:created"
        )
        await client.update_incident(
            incident_urn="urn:li:incident:created",
            title="Updated regression",
            description="Latest Histograph evidence",
        )
        await client.resolve_incident(
            incident_urn="urn:li:incident:created",
            message="Verified by Histograph",
        )
        assert len(requests) == 5
    finally:
        await http_client.aclose()


@pytest.mark.asyncio
async def test_datahub_graphql_surfaces_sanitized_errors() -> None:
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"errors": [{"message": "permission denied"}]})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = DataHubGraphqlClient(
        endpoint_url="https://datahub.example",
        token="datahub-token",
        http_client=http_client,
    )
    try:
        with pytest.raises(DataHubGraphqlError, match="permission denied"):
            await client.verify()
    finally:
        await http_client.aclose()
