import asyncio
import hashlib
import json
import os
from dataclasses import dataclass, field
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from histograph.api.config import Settings
from histograph.api.database.models import (
    AgentTargetRecord,
    BaselineDependencyRecord,
    BaselineVersionRecord,
    DataHubConnectionRecord,
    ProtectedQuestionRecord,
    RunRecord,
)
from histograph.api.database.models.common import BaselineStatus, ConnectionStatus, RunStatus
from histograph.api.database.session import create_database
from histograph.api.main import create_app
from histograph.domain import AgentEvent, AgentEventType, DataHubContextSnapshot
from histograph.runner import Runner
from histograph.security import EnvelopeCipher, generate_encryption_key
from histograph.storage import StoredArtifact
from histograph.worker.activities import RunActivities
from histograph.workflows import RunWorkflowInput


@dataclass
class RecordingOrchestrator:
    started_runs: list[str] = field(default_factory=list)

    async def start_run(self, run_id: str) -> str:
        self.started_runs.append(run_id)
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


class DataHubProvider:
    asset_urn = "urn:li:dataset:(urn:li:dataPlatform:postgres,finance.net_revenue,PROD)"

    async def verify(self) -> tuple[str, ...]:
        return "search", "get_entities", "get_lineage"

    async def search_context(
        self,
        question: str,
        context_query: str | None = None,
        limit: int = 10,
    ) -> DataHubContextSnapshot:
        return DataHubContextSnapshot(
            query="/q net+revenue",
            asset_urns=(self.asset_urn,),
        )


class AnalyticsAgent:
    async def health(self) -> None:
        return None

    async def invoke(self, question: str, trace_id: str) -> tuple[AgentEvent, ...]:
        return (
            AgentEvent(
                sequence=0,
                type=AgentEventType.TOOL_RESULT,
                trace_id=trace_id,
                payload={
                    "tool_name": "get_entities",
                    "result": {"urn": DataHubProvider.asset_urn},
                },
            ),
            AgentEvent(
                sequence=1,
                type=AgentEventType.SQL,
                trace_id=trace_id,
                payload={
                    "sql": (
                        "SELECT country, SUM(net_revenue) AS net_revenue "
                        "FROM finance.net_revenue GROUP BY country"
                    ),
                    "columns": ["country", "net_revenue"],
                    "rows": [["NG", 140]],
                },
            ),
            AgentEvent(
                sequence=2,
                type=AgentEventType.COMPLETE,
                trace_id=trace_id,
                payload={"text": "Net revenue was $140."},
            ),
        )


class InMemoryArtifactStore:
    async def put_json(self, object_key: str, value: object) -> StoredArtifact:
        payload = json.dumps(value, sort_keys=True, default=str).encode()
        return StoredArtifact(
            object_key=object_key,
            sha256=hashlib.sha256(payload).hexdigest(),
            content_type="application/json",
            size_bytes=len(payload),
        )


def test_baseline_capture_approval_and_protected_run(monkeypatch: pytest.MonkeyPatch) -> None:
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
    orchestrator = RecordingOrchestrator()
    app = create_app(settings=settings, orchestrator=orchestrator)
    headers = {"Authorization": "Bearer test-bootstrap-token"}
    suffix = uuid4().hex[:10]

    with TestClient(app) as client:
        organization = client.post(
            "/v1/organizations",
            headers=headers,
            json={
                "name": "Baseline Lifecycle Organization",
                "slug": f"baseline-lifecycle-{suffix}",
                "owner_email": "owner@example.com",
                "owner_display_name": "Test Owner",
            },
        ).json()
        project = client.post(
            "/v1/projects",
            headers=headers,
            json={
                "organization_id": organization["id"],
                "name": "Revenue Assurance",
                "slug": f"revenue-assurance-{suffix}",
                "environment": "staging",
                "timezone": "UTC",
            },
        ).json()
        connection = client.post(
            f"/v1/projects/{project['id']}/datahub-connections",
            headers=headers,
            json={
                "name": "Staging DataHub",
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
                "adapter_type": "datahub_analytics_agent",
                "base_url": "https://agent.example.com",
                "engine_name": "warehouse",
                "secret_location": "managed",
            },
        ).json()
        suite = client.post(
            f"/v1/projects/{project['id']}/test-suites",
            headers=headers,
            json={
                "name": "Executive metrics",
                "slug": f"executive-metrics-{suffix}",
            },
        ).json()

        async def mark_integrations_ready() -> None:
            engine, session_factory = create_database(settings)
            try:
                async with session_factory() as session:
                    connection_record = await session.get(DataHubConnectionRecord, connection["id"])
                    target_record = await session.get(AgentTargetRecord, target["id"])
                    assert connection_record is not None
                    assert target_record is not None
                    connection_record.status = ConnectionStatus.READY
                    target_record.status = ConnectionStatus.READY
                    await session.commit()
            finally:
                await engine.dispose()

        asyncio.run(mark_integrations_ready())
        question_response = client.post(
            f"/v1/projects/{project['id']}/test-suites/{suite['id']}/protected-questions",
            headers=headers,
            json={
                "stable_key": f"net-revenue-{suffix}",
                "name": "Net revenue",
                "criticality": "high",
                "agent_target_id": target["id"],
                "question": "What was net revenue by country last month?",
                "assets": {"required": [DataHubProvider.asset_urn]},
                "sql": {"required_tables": ["finance.net_revenue"]},
                "result": {
                    "required_columns": ["country", "net_revenue"],
                    "min_rows": 1,
                },
                "response": {"required_phrases": ["net revenue"]},
            },
        )
        assert question_response.status_code == 201
        question = question_response.json()
        baseline_run_response = client.post(
            f"/v1/projects/{project['id']}/protected-questions/{question['id']}/baseline-runs",
            headers={**headers, "Idempotency-Key": f"baseline-capture-{suffix}"},
        )
        assert baseline_run_response.status_code == 202
        baseline_run_id = baseline_run_response.json()["id"]

        monkeypatch.setattr("histograph.worker.activities.activity.heartbeat", lambda _: None)

        async def execute_run(run_id: str) -> None:
            engine, session_factory = create_database(settings)
            activities = RunActivities(
                session_factory,
                EnvelopeCipher.from_config(encryption_key),
                InMemoryArtifactStore(),
                Runner(
                    datahub_factory=lambda _: DataHubProvider(),
                    agent_factory=lambda _: AnalyticsAgent(),
                ),
            )
            try:
                request = RunWorkflowInput(run_id=run_id)
                plan = await activities.plan_run(request)
                assert plan.action_required is False
                assert plan.selected_test_count == 1
                summary = await activities.execute_selected_tests(request)
                assert summary.passed == 1
                await activities.report_run(request, summary)
            finally:
                await engine.dispose()

        asyncio.run(execute_run(baseline_run_id))
        baselines_response = client.get(
            f"/v1/projects/{project['id']}/protected-questions/{question['id']}/baselines",
            headers=headers,
        )
        assert baselines_response.status_code == 200
        baselines = baselines_response.json()
        assert len(baselines) == 1
        assert baselines[0]["status"] == "draft"
        approval = client.post(
            (
                f"/v1/projects/{project['id']}/protected-questions/{question['id']}"
                f"/baselines/{baselines[0]['id']}/approve"
            ),
            headers=headers,
            json={"justification": "Validated against the staging warehouse results."},
        )
        assert approval.status_code == 200
        assert approval.json()["status"] == "approved"
        protected_run = client.post(
            f"/v1/projects/{project['id']}/runs",
            headers={**headers, "Idempotency-Key": f"protected-run-{suffix}"},
            json={
                "trigger_type": "api",
                "selection": {"test_ids": [question["id"]]},
            },
        )
        assert protected_run.status_code == 202
        protected_run_id = protected_run.json()["id"]

        asyncio.run(execute_run(protected_run_id))

    async def verify_lifecycle() -> None:
        engine, session_factory = create_database(settings)
        try:
            async with session_factory() as session:
                question_record = await session.get(ProtectedQuestionRecord, question["id"])
                baseline = await session.scalar(
                    select(BaselineVersionRecord).where(
                        BaselineVersionRecord.protected_question_id == question["id"]
                    )
                )
                dependencies = tuple(
                    await session.scalars(
                        select(BaselineDependencyRecord).where(
                            BaselineDependencyRecord.baseline_version_id == baseline.id
                        )
                    )
                )
                protected_run_record = await session.get(RunRecord, protected_run_id)
                assert question_record is not None
                assert baseline is not None
                assert question_record.active_baseline_id == baseline.id
                assert baseline.status is BaselineStatus.APPROVED
                assert [dependency.asset_urn for dependency in dependencies] == [
                    DataHubProvider.asset_urn
                ]
                assert protected_run_record is not None
                assert protected_run_record.status is RunStatus.PASSED
        finally:
            await engine.dispose()

    asyncio.run(verify_lifecycle())
