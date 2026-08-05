import asyncio
import os
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from histograph_api.config import Settings
from histograph_api.database.models import DataHubConnectionRecord
from histograph_api.database.models.common import ConnectionStatus
from histograph_api.database.session import create_database
from histograph_api.main import create_app
from histograph_security import generate_encryption_key
from sqlalchemy import select


@dataclass
class RecordingOrchestrator:
    started_runs: list[str] = field(default_factory=list)
    cancelled_runs: list[str] = field(default_factory=list)
    schedules: list[str] = field(default_factory=list)

    async def start_run(self, run_id: str) -> str:
        self.started_runs.append(run_id)
        return f"histograph/run/{run_id}"

    async def cancel_run(self, workflow_id: str) -> None:
        self.cancelled_runs.append(workflow_id)

    async def create_schedule(
        self,
        schedule_id: str,
        cron_expression: str,
        timezone: str,
        overlap_policy: str,
    ) -> None:
        self.schedules.append(schedule_id)

    async def delete_schedule(self, schedule_id: str) -> None:
        self.schedules.remove(schedule_id)

    async def close(self) -> None:
        return None


def test_control_plane_encrypts_connections_and_queues_idempotent_runs() -> None:
    database_url = os.getenv("HISTOGRAPH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HISTOGRAPH_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    settings = Settings(
        environment="test",
        database_url=database_url,
        encryption_keys=generate_encryption_key("test-v1"),
        token_pepper="test-token-pepper-that-is-longer-than-thirty-two-characters",
        bootstrap_token="test-bootstrap-token",
    )
    orchestrator = RecordingOrchestrator()
    app = create_app(settings=settings, orchestrator=orchestrator)
    headers = {"Authorization": "Bearer test-bootstrap-token"}
    datahub_token = "datahub-token-that-must-never-be-stored-in-plaintext"
    suffix = uuid4().hex[:10]

    with TestClient(app) as client:
        organization = client.post(
            "/v1/organizations",
            headers=headers,
            json={
                "name": "Histograph Test Organization",
                "slug": f"histograph-test-{suffix}",
                "owner_email": "owner@example.com",
                "owner_display_name": "Test Owner",
            },
        )
        assert organization.status_code == 201
        organization_id = organization.json()["id"]
        project_response = client.post(
            "/v1/projects",
            headers=headers,
            json={
                "organization_id": organization_id,
                "name": "Revenue Agent",
                "slug": "revenue-agent",
                "environment": "production",
                "timezone": "UTC",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]
        private_runner_response = client.post(
            f"/v1/projects/{project_id}/datahub-connections",
            headers=headers,
            json={
                "name": "Unsupported private runner",
                "mode": "self_hosted",
                "endpoint_url": "https://datahub.internal",
                "mcp_url": "https://datahub.internal/integrations/ai/mcp",
                "secret_location": "private_runner",
            },
        )
        assert private_runner_response.status_code == 422
        connection_response = client.post(
            f"/v1/projects/{project_id}/datahub-connections",
            headers=headers,
            json={
                "name": "Production DataHub",
                "mode": "cloud",
                "endpoint_url": "https://datahub.example.com",
                "mcp_url": "https://datahub.example.com/integrations/ai/mcp",
                "secret_location": "managed",
                "token": datahub_token,
            },
        )
        assert connection_response.status_code == 201
        assert datahub_token not in connection_response.text

        async def mark_connection_ready() -> None:
            engine, session_factory = create_database(settings)
            try:
                async with session_factory() as session:
                    connection = await session.get(
                        DataHubConnectionRecord, connection_response.json()["id"]
                    )
                    assert connection is not None
                    connection.status = ConnectionStatus.READY
                    await session.commit()
            finally:
                await engine.dispose()

        asyncio.run(mark_connection_ready())

        run_headers = {**headers, "Idempotency-Key": "integration-run-0001"}
        first_run = client.post(
            f"/v1/projects/{project_id}/runs",
            headers=run_headers,
            json={
                "trigger_type": "api",
                "selection": {"all_active": True},
            },
        )
        assert first_run.status_code == 202
        repeated_run = client.post(
            f"/v1/projects/{project_id}/runs",
            headers=run_headers,
            json={
                "trigger_type": "api",
                "selection": {"all_active": True},
            },
        )
        assert repeated_run.status_code == 202
        assert repeated_run.json()["id"] == first_run.json()["id"]
        assert orchestrator.started_runs == [first_run.json()["id"]]

    async def read_encrypted_secret() -> str | None:
        engine, session_factory = create_database(settings)
        try:
            async with session_factory() as session:
                return await session.scalar(
                    select(DataHubConnectionRecord.encrypted_credentials).where(
                        DataHubConnectionRecord.project_id == project_id
                    )
                )
        finally:
            await engine.dispose()

    encrypted_secret = asyncio.run(read_encrypted_secret())
    assert encrypted_secret is not None
    assert datahub_token not in encrypted_secret


def test_service_identities_cannot_escalate_beyond_their_scope() -> None:
    database_url = os.getenv("HISTOGRAPH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HISTOGRAPH_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    settings = Settings(
        environment="test",
        database_url=database_url,
        encryption_keys=generate_encryption_key("test-v1"),
        token_pepper="test-token-pepper-that-is-longer-than-thirty-two-characters",
        bootstrap_token="test-bootstrap-token",
    )
    app = create_app(settings=settings, orchestrator=RecordingOrchestrator())
    bootstrap_headers = {"Authorization": "Bearer test-bootstrap-token"}
    suffix = uuid4().hex[:10]

    with TestClient(app) as client:
        organization_response = client.post(
            "/v1/organizations",
            headers=bootstrap_headers,
            json={
                "name": "Service Scope Organization",
                "slug": f"service-scope-{suffix}",
                "owner_email": "owner@example.com",
                "owner_display_name": "Test Owner",
            },
        )
        assert organization_response.status_code == 201
        organization_id = organization_response.json()["id"]
        project_response = client.post(
            "/v1/projects",
            headers=bootstrap_headers,
            json={
                "organization_id": organization_id,
                "name": "Protected Project",
                "slug": f"protected-project-{suffix}",
                "environment": "production",
                "timezone": "UTC",
            },
        )
        assert project_response.status_code == 201
        project_id = project_response.json()["id"]
        identity_response = client.post(
            f"/v1/organizations/{organization_id}/service-identities",
            headers=bootstrap_headers,
            json={
                "name": "DataHub event bridge",
                "project_id": project_id,
                "scopes": ["metadata-events:write"],
            },
        )
        assert identity_response.status_code == 201
        service_headers = {"Authorization": f"Bearer {identity_response.json()['token']}"}

        project_read = client.get(f"/v1/projects/{project_id}", headers=service_headers)
        assert project_read.status_code == 200
        project_write = client.patch(
            f"/v1/projects/{project_id}",
            headers=service_headers,
            json={"name": "Escalated name"},
        )
        assert project_write.status_code == 403
        organization_read = client.get(
            f"/v1/organizations/{organization_id}", headers=service_headers
        )
        assert organization_read.status_code == 404
        organization_create = client.post(
            "/v1/organizations",
            headers=service_headers,
            json={
                "name": "Unauthorized Organization",
                "slug": f"unauthorized-{suffix}",
                "owner_email": "attacker@example.com",
                "owner_display_name": "Unauthorized",
            },
        )
        assert organization_create.status_code == 403
