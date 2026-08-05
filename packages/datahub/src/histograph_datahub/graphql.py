from typing import Any

import httpx


class DataHubGraphqlError(RuntimeError):
    pass


class DataHubGraphqlClient:
    def __init__(
        self,
        *,
        endpoint_url: str,
        token: str,
        http_client: httpx.AsyncClient | None = None,
    ):
        endpoint = endpoint_url.rstrip("/")
        self._graphql_url = (
            endpoint if endpoint.endswith("/api/graphql") else f"{endpoint}/api/graphql"
        )
        self._token = token
        self._http = http_client or httpx.AsyncClient(timeout=30, follow_redirects=True)
        self._owns_http_client = http_client is None

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http.aclose()

    async def verify(self) -> str:
        payload = await self._execute(
            """
            query HistographVerifyDataHub {
              me {
                corpUser {
                  urn
                }
              }
            }
            """,
            {},
        )
        me = payload.get("me")
        corp_user = me.get("corpUser") if isinstance(me, dict) else None
        urn = corp_user.get("urn") if isinstance(corp_user, dict) else None
        if not isinstance(urn, str):
            raise DataHubGraphqlError("DataHub GraphQL did not identify the authenticated actor")
        return urn

    async def find_owned_active_incident(
        self,
        *,
        resource_urn: str,
        ownership_marker: str,
    ) -> str | None:
        payload = await self._execute(
            """
            query HistographActiveIncidents($urn: String!) {
              dataset(urn: $urn) {
                incidents(state: ACTIVE, start: 0, count: 100) {
                  incidents {
                    urn
                    title
                    description
                  }
                }
              }
            }
            """,
            {"urn": resource_urn},
        )
        dataset = payload.get("dataset")
        if not isinstance(dataset, dict):
            return None
        result = dataset.get("incidents")
        incidents = result.get("incidents", []) if isinstance(result, dict) else []
        for incident in incidents:
            if not isinstance(incident, dict):
                continue
            searchable = f"{incident.get('title', '')}\n{incident.get('description', '')}"
            urn = incident.get("urn")
            if ownership_marker in searchable and isinstance(urn, str):
                return urn
        return None

    async def raise_incident(
        self,
        *,
        resource_urn: str,
        title: str,
        description: str,
    ) -> str:
        payload = await self._execute(
            """
            mutation HistographRaiseIncident($input: RaiseIncidentInput!) {
              raiseIncident(input: $input)
            }
            """,
            {
                "input": {
                    "type": "CUSTOM",
                    "customType": "HISTOGRAPH_AGENT_REGRESSION",
                    "title": title,
                    "description": description,
                    "resourceUrn": resource_urn,
                }
            },
        )
        urn = payload.get("raiseIncident")
        if not isinstance(urn, str) or not urn.startswith("urn:li:incident:"):
            raise DataHubGraphqlError("DataHub did not return an incident URN")
        return urn

    async def resolve_incident(self, *, incident_urn: str, message: str) -> None:
        await self.update_incident_status(
            incident_urn=incident_urn,
            state="RESOLVED",
            message=message,
        )

    async def reopen_incident(self, *, incident_urn: str, message: str) -> None:
        await self.update_incident_status(
            incident_urn=incident_urn,
            state="ACTIVE",
            message=message,
        )

    async def update_incident(
        self,
        *,
        incident_urn: str,
        title: str,
        description: str,
    ) -> None:
        payload = await self._execute(
            """
            mutation HistographUpdateIncident($urn: String!, $input: UpdateIncidentInput!) {
              updateIncident(urn: $urn, input: $input)
            }
            """,
            {
                "urn": incident_urn,
                "input": {"title": title, "description": description},
            },
        )
        if payload.get("updateIncident") in {None, False, "false"}:
            raise DataHubGraphqlError("DataHub did not confirm the incident update")

    async def update_incident_status(
        self,
        *,
        incident_urn: str,
        state: str,
        message: str,
    ) -> None:
        payload = await self._execute(
            """
            mutation HistographResolveIncident($urn: String!, $input: UpdateIncidentStatusInput!) {
              updateIncidentStatus(urn: $urn, input: $input)
            }
            """,
            {
                "urn": incident_urn,
                "input": {"state": state, "message": message},
            },
        )
        result = payload.get("updateIncidentStatus")
        if result not in {True, "true", incident_urn}:
            raise DataHubGraphqlError("DataHub did not confirm the incident status update")

    async def _execute(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        response = await self._http.post(
            self._graphql_url,
            headers={
                "Accept": "application/json",
                "Authorization": f"Bearer {self._token}",
                "Content-Type": "application/json",
            },
            json={"query": query, "variables": variables},
        )
        if response.is_error:
            request_id = response.headers.get("x-request-id", "unknown")
            raise DataHubGraphqlError(
                f"DataHub GraphQL returned {response.status_code} (request {request_id})"
            )
        try:
            payload = response.json()
        except ValueError as error:
            raise DataHubGraphqlError("DataHub GraphQL returned invalid JSON") from error
        errors = payload.get("errors")
        if errors:
            messages = [
                item.get("message", "unknown error") for item in errors if isinstance(item, dict)
            ]
            detail = "; ".join(messages) or "unknown error"
            raise DataHubGraphqlError(f"DataHub GraphQL failed: {detail[:1000]}")
        data = payload.get("data")
        if not isinstance(data, dict):
            raise DataHubGraphqlError("DataHub GraphQL response did not contain data")
        return data
