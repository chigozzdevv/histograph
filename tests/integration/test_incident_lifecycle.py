import asyncio
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from histograph.api.config import Settings
from histograph.api.database.models import (
    DataHubConnectionRecord,
    DataHubWritebackRecord,
    IncidentOccurrenceRecord,
    IncidentRecord,
    ProtectedQuestionRecord,
    RunRecord,
)
from histograph.api.database.models import (
    TestExecutionRecord as ExecutionRecord,
)
from histograph.api.database.models import (
    TestVersionRecord as VersionRecord,
)
from histograph.api.database.models.common import (
    ConnectionStatus,
    ExecutionStatus,
    IncidentStatus,
    RunStatus,
    TriggerType,
)
from histograph.api.database.session import create_database
from histograph.api.main import create_app
from histograph.security import EnvelopeCipher, generate_encryption_key, stable_fingerprint
from histograph.worker.incidents import IncidentManager


@dataclass
class Orchestrator:
    async def start_run(self, run_id: str) -> str:
        return f"histograph/run/{run_id}"

    async def cancel_run(self, workflow_id: str) -> None:
        return None

    async def create_schedule(
        self,
        schedule_id: str,
        cron_expression: str,
        timezone: str,
        overlap_policy: str,
    ) -> None:
        return None

    async def delete_schedule(self, schedule_id: str) -> None:
        return None

    async def close(self) -> None:
        return None


class DataHubIncidentClient:
    incident_urn = "urn:li:incident:histograph-test"

    def __init__(self) -> None:
        self.raise_attempts = 0
        self.update_calls = 0
        self.reopen_calls = 0
        self.resolve_calls = 0
        self.close_calls = 0
        self.fail_first_raise = True

    async def close(self) -> None:
        self.close_calls += 1

    async def find_owned_active_incident(
        self, *, resource_urn: str, ownership_marker: str
    ) -> str | None:
        return None

    async def raise_incident(self, *, resource_urn: str, title: str, description: str) -> str:
        self.raise_attempts += 1
        if self.fail_first_raise:
            self.fail_first_raise = False
            raise RuntimeError("temporary DataHub write failure")
        return self.incident_urn

    async def update_incident(self, *, incident_urn: str, title: str, description: str) -> None:
        self.update_calls += 1

    async def reopen_incident(self, *, incident_urn: str, message: str) -> None:
        self.reopen_calls += 1

    async def resolve_incident(self, *, incident_urn: str, message: str) -> None:
        self.resolve_calls += 1


def test_incident_writeback_retries_resolves_and_reopens() -> None:
    database_url = os.getenv("HISTOGRAPH_TEST_DATABASE_URL")
    if not database_url:
        pytest.skip("HISTOGRAPH_TEST_DATABASE_URL is required for PostgreSQL integration tests")
    encryption_key = generate_encryption_key("test-v1")
    settings = Settings(
        environment="test",
        database_url=database_url,
        encryption_keys=encryption_key,
        token_pepper="test-token-pepper-that-is-longer-than-thirty-two-characters",
        bootstrap_token="test-bootstrap-token",
    )
    app = create_app(settings=settings, orchestrator=Orchestrator())
    headers = {"Authorization": "Bearer test-bootstrap-token"}
    suffix = uuid4().hex[:10]
    asset_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,finance.revenue,PROD)"

    with TestClient(app) as client:
        organization = client.post(
            "/v1/organizations",
            headers=headers,
            json={
                "name": "Incident Lifecycle Organization",
                "slug": f"incident-lifecycle-{suffix}",
                "owner_email": "owner@example.com",
                "owner_display_name": "Test Owner",
            },
        ).json()
        project = client.post(
            "/v1/projects",
            headers=headers,
            json={
                "organization_id": organization["id"],
                "name": "Production Revenue Assurance",
                "slug": f"production-revenue-{suffix}",
                "environment": "production",
                "timezone": "UTC",
            },
        ).json()
        connection = client.post(
            f"/v1/projects/{project['id']}/datahub-connections",
            headers=headers,
            json={
                "name": "Production DataHub",
                "mode": "cloud",
                "endpoint_url": "https://datahub.example.com",
                "mcp_url": "https://datahub.example.com/integrations/ai/mcp",
                "secret_location": "managed",
                "token": "datahub-token",
            },
        ).json()
        target = client.post(
            f"/v1/projects/{project['id']}/agent-targets",
            headers=headers,
            json={
                "name": "Revenue agent",
                "base_url": "https://agent.example.com",
                "engine_name": "warehouse",
            },
        ).json()
        suite = client.post(
            f"/v1/projects/{project['id']}/test-suites",
            headers=headers,
            json={"name": "Executive metrics", "slug": f"executive-metrics-{suffix}"},
        ).json()
        question = client.post(
            f"/v1/projects/{project['id']}/test-suites/{suite['id']}/protected-questions",
            headers=headers,
            json={
                "stable_key": f"net-revenue-{suffix}",
                "name": "Net revenue",
                "agent_target_id": target["id"],
                "question": "What was net revenue?",
            },
        ).json()

    async def prepare() -> tuple[str, str, str, str]:
        engine, session_factory = create_database(settings)
        try:
            async with session_factory() as session:
                connection_record = await session.get(DataHubConnectionRecord, connection["id"])
                question_record = await session.get(ProtectedQuestionRecord, question["id"])
                assert connection_record is not None
                assert question_record is not None
                connection_record.status = ConnectionStatus.READY
                version = await session.get(VersionRecord, question_record.active_version_id)
                assert version is not None
                await session.commit()
                return (
                    organization["id"],
                    project["id"],
                    question_record.id,
                    version.id,
                )
        finally:
            await engine.dispose()

    organization_id, project_id, question_id, version_id = asyncio.run(prepare())

    async def create_execution(status: ExecutionStatus, label: str) -> str:
        engine, session_factory = create_database(settings)
        try:
            async with session_factory() as session:
                run = RunRecord(
                    organization_id=organization_id,
                    project_id=project_id,
                    trigger_type=TriggerType.API,
                    trigger_reference=label,
                    idempotency_key=f"incident-{label}-{suffix}",
                    requested_by="test",
                    status=(
                        RunStatus.PASSED if status is ExecutionStatus.PASSED else RunStatus.FAILED
                    ),
                    configuration_fingerprint=stable_fingerprint({"label": label}),
                    selection_json={},
                    report_json={"status": status.value},
                    queued_at=datetime.now(UTC),
                    started_at=datetime.now(UTC),
                    completed_at=datetime.now(UTC),
                )
                session.add(run)
                await session.flush()
                session.add(
                    ExecutionRecord(
                        organization_id=organization_id,
                        project_id=project_id,
                        run_id=run.id,
                        protected_question_id=question_id,
                        test_version_id=version_id,
                        baseline_version_id=None,
                        agent_target_id=target["id"],
                        status=status,
                        attempt_count=1,
                        trace_id=f"trace-{label}",
                        evidence_json={"selected_asset_urns": [asset_urn]},
                        evaluation_json=(
                            {
                                "status": "failed",
                                "findings": [
                                    {
                                        "code": "response.phrase-required",
                                        "passed": False,
                                    }
                                ],
                            }
                            if status is ExecutionStatus.FAILED
                            else {"status": "passed", "findings": []}
                        ),
                        started_at=datetime.now(UTC),
                        completed_at=datetime.now(UTC),
                    )
                )
                await session.commit()
                return run.id
        finally:
            await engine.dispose()

    failed_run = asyncio.run(create_execution(ExecutionStatus.FAILED, "failure-one"))
    success_one = asyncio.run(create_execution(ExecutionStatus.PASSED, "success-one"))
    success_two = asyncio.run(create_execution(ExecutionStatus.PASSED, "success-two"))
    reopened_run = asyncio.run(create_execution(ExecutionStatus.FAILED, "failure-two"))
    datahub = DataHubIncidentClient()

    async def exercise_manager() -> None:
        engine, session_factory = create_database(settings)
        manager = IncidentManager(
            session_factory,
            EnvelopeCipher.from_config(encryption_key),
            "https://histograph.example.com",
            client_factory=lambda **_: datahub,
        )
        try:
            with pytest.raises(RuntimeError, match="temporary DataHub write failure"):
                await manager.process_run(failed_run)
            await manager.process_run(failed_run)
            await manager.process_run(failed_run)
            await manager.process_run(success_one)
            await manager.process_run(success_two)
            await manager.process_run(reopened_run)
        finally:
            await engine.dispose()

    asyncio.run(exercise_manager())

    async def verify() -> None:
        engine, session_factory = create_database(settings)
        try:
            async with session_factory() as session:
                incidents = tuple(
                    await session.scalars(
                        select(IncidentRecord).where(IncidentRecord.project_id == project_id)
                    )
                )
                assert len(incidents) == 1
                incident = incidents[0]
                occurrences = tuple(
                    await session.scalars(
                        select(IncidentOccurrenceRecord).where(
                            IncidentOccurrenceRecord.incident_id == incident.id
                        )
                    )
                )
                writebacks = tuple(
                    await session.scalars(
                        select(DataHubWritebackRecord)
                        .where(DataHubWritebackRecord.incident_id == incident.id)
                        .order_by(DataHubWritebackRecord.created_at)
                    )
                )
                assert incident.status is IncidentStatus.OPEN
                assert incident.occurrence_count == 2
                assert incident.consecutive_success_count == 0
                assert incident.datahub_incident_urn == datahub.incident_urn
                assert len(occurrences) == 4
                assert [writeback.operation for writeback in writebacks] == [
                    "raise",
                    "resolve",
                    "reopen",
                ]
                assert all(writeback.status == "succeeded" for writeback in writebacks)
                assert writebacks[0].attempt_count == 2
        finally:
            await engine.dispose()

    asyncio.run(verify())
    assert datahub.raise_attempts == 2
    assert datahub.resolve_calls == 1
    assert datahub.reopen_calls == 1
    assert datahub.update_calls == 1
