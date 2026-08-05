from collections.abc import Callable
from datetime import UTC, datetime
from typing import Protocol

from histograph_api.database.models import (
    AuditEventRecord,
    BaselineDependencyRecord,
    DataHubConnectionRecord,
    DataHubWritebackRecord,
    IncidentOccurrenceRecord,
    IncidentRecord,
    ProjectRecord,
    ProtectedQuestionRecord,
    RunRecord,
    TestExecutionRecord,
)
from histograph_api.database.models.common import (
    ConnectionStatus,
    ExecutionStatus,
    IncidentStatus,
    ProjectEnvironment,
    SecretLocation,
    TriggerType,
)
from histograph_datahub import DataHubGraphqlClient
from histograph_security import EnvelopeCipher, stable_fingerprint
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker


class IncidentClient(Protocol):
    async def close(self) -> None: ...

    async def find_owned_active_incident(
        self, *, resource_urn: str, ownership_marker: str
    ) -> str | None: ...

    async def raise_incident(self, *, resource_urn: str, title: str, description: str) -> str: ...

    async def reopen_incident(self, *, incident_urn: str, message: str) -> None: ...

    async def update_incident(self, *, incident_urn: str, title: str, description: str) -> None: ...

    async def resolve_incident(self, *, incident_urn: str, message: str) -> None: ...


class IncidentManager:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: EnvelopeCipher,
        public_app_url: str,
        client_factory: Callable[..., IncidentClient] = DataHubGraphqlClient,
    ):
        self._session_factory = session_factory
        self._cipher = cipher
        self._public_app_url = public_app_url.rstrip("/")
        self._client_factory = client_factory

    async def process_run(self, run_id: str) -> None:
        context = await self._load_context(run_id)
        if context is None:
            return
        run, project, connection, executions = context
        token = self._cipher.decrypt(
            connection.encrypted_credentials,
            context=f"histograph:datahub:{run.project_id}:{connection.id}",
        )
        client: IncidentClient = self._client_factory(
            endpoint_url=connection.endpoint_url,
            token=token,
        )
        try:
            for execution in executions:
                if execution.status in {ExecutionStatus.FAILED, ExecutionStatus.ERROR}:
                    await self._record_failure(run, execution, client)
                elif execution.status is ExecutionStatus.PASSED:
                    await self._record_success(run, project, execution, client)
        finally:
            await client.close()

    async def _load_context(
        self, run_id: str
    ) -> (
        tuple[
            RunRecord,
            ProjectRecord,
            DataHubConnectionRecord,
            tuple[TestExecutionRecord, ...],
        ]
        | None
    ):
        async with self._session_factory() as session:
            run = await session.get(RunRecord, run_id)
            if (
                run is None
                or run.trigger_type is TriggerType.GITHUB_PULL_REQUEST
                or run.selection_json.get("baseline_capture")
            ):
                return None
            project = await session.get(ProjectRecord, run.project_id)
            if project is None or project.environment is not ProjectEnvironment.PRODUCTION:
                return None
            policy = project.default_trigger_policy_json.get("datahub_writeback", {})
            if isinstance(policy, dict) and policy.get("incidents") is False:
                return None
            connection = await session.scalar(
                select(DataHubConnectionRecord).where(
                    DataHubConnectionRecord.project_id == run.project_id,
                    DataHubConnectionRecord.active.is_(True),
                    DataHubConnectionRecord.deleted_at.is_(None),
                )
            )
            if (
                connection is None
                or connection.status is not ConnectionStatus.READY
                or connection.secret_location is not SecretLocation.MANAGED
                or not connection.encrypted_credentials
            ):
                raise RuntimeError(
                    "Production incident writeback requires a managed DataHub connection"
                )
            executions = tuple(
                await session.scalars(
                    select(TestExecutionRecord)
                    .where(TestExecutionRecord.run_id == run.id)
                    .order_by(TestExecutionRecord.id)
                )
            )
            return run, project, connection, executions

    async def _record_failure(
        self,
        run: RunRecord,
        execution: TestExecutionRecord,
        client: IncidentClient,
    ) -> None:
        assets = await self._execution_assets(execution)
        finding_codes = _failed_finding_codes(execution)
        for asset_urn in assets:
            fingerprint = stable_fingerprint(
                {
                    "project_id": run.project_id,
                    "protected_question_id": execution.protected_question_id,
                    "asset_urn": asset_urn,
                    "finding_codes": finding_codes,
                }
            )
            incident, occurrence_created, was_resolved = await self._upsert_failure(
                run,
                execution,
                asset_urn,
                fingerprint,
                finding_codes,
            )
            if occurrence_created:
                operation = (
                    "reopen"
                    if was_resolved and incident.datahub_incident_urn
                    else ("update" if incident.datahub_incident_urn else "raise")
                )
            else:
                operation = await self._retryable_failure_operation(
                    run,
                    incident,
                    execution,
                )
                if operation is None:
                    continue
            await self._write_failure(client, run, incident, operation)

    async def _upsert_failure(
        self,
        run: RunRecord,
        execution: TestExecutionRecord,
        asset_urn: str,
        fingerprint: str,
        finding_codes: tuple[str, ...],
    ) -> tuple[IncidentRecord, bool, bool]:
        async with self._session_factory() as session:
            incident = await session.scalar(
                select(IncidentRecord)
                .where(
                    IncidentRecord.organization_id == run.organization_id,
                    IncidentRecord.project_id == run.project_id,
                    IncidentRecord.fingerprint == fingerprint,
                )
                .with_for_update()
            )
            was_resolved = incident is not None and incident.status is IncidentStatus.RESOLVED
            if incident is None:
                question = await session.get(
                    ProtectedQuestionRecord, execution.protected_question_id
                )
                incident = IncidentRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    protected_question_id=execution.protected_question_id,
                    fingerprint=fingerprint,
                    status=IncidentStatus.OPEN,
                    title=(
                        f"Agent regression: {question.name if question else 'protected question'}"
                    ),
                    summary=_failure_summary(finding_codes),
                    resource_urn=asset_urn,
                    first_run_id=run.id,
                    latest_run_id=run.id,
                    occurrence_count=0,
                    consecutive_success_count=0,
                )
                session.add(incident)
                await session.flush()
            occurrence = await session.scalar(
                select(IncidentOccurrenceRecord).where(
                    IncidentOccurrenceRecord.incident_id == incident.id,
                    IncidentOccurrenceRecord.run_id == run.id,
                    IncidentOccurrenceRecord.test_execution_id == execution.id,
                    IncidentOccurrenceRecord.occurrence_type == "failure",
                )
            )
            if occurrence:
                return incident, False, was_resolved
            session.add(
                IncidentOccurrenceRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    incident_id=incident.id,
                    run_id=run.id,
                    test_execution_id=execution.id,
                    occurrence_type="failure",
                    evidence_json={
                        "finding_codes": list(finding_codes),
                        "evaluation": execution.evaluation_json or {},
                        "previous_status": "resolved" if was_resolved else "open",
                    },
                )
            )
            incident.status = IncidentStatus.OPEN
            incident.resolved_at = None
            incident.latest_run_id = run.id
            incident.occurrence_count += 1
            incident.consecutive_success_count = 0
            session.add(
                AuditEventRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    actor_type="worker",
                    actor_id="histograph-incident-manager",
                    action="incident.reopened" if was_resolved else "incident.recorded",
                    target_type="incident",
                    target_id=incident.id,
                    request_id=run.id,
                    details_json={"run_id": run.id, "resource_urn": asset_urn},
                )
            )
            await session.commit()
            return incident, True, was_resolved

    async def _retryable_failure_operation(
        self,
        run: RunRecord,
        incident: IncidentRecord,
        execution: TestExecutionRecord,
    ) -> str | None:
        async with self._session_factory() as session:
            writeback = await session.scalar(
                select(DataHubWritebackRecord)
                .where(
                    DataHubWritebackRecord.run_id == run.id,
                    DataHubWritebackRecord.incident_id == incident.id,
                    DataHubWritebackRecord.operation.in_(("raise", "update", "reopen")),
                )
                .order_by(DataHubWritebackRecord.created_at.desc())
            )
            if writeback:
                return None if writeback.status == "succeeded" else writeback.operation
            occurrence = await session.scalar(
                select(IncidentOccurrenceRecord).where(
                    IncidentOccurrenceRecord.incident_id == incident.id,
                    IncidentOccurrenceRecord.run_id == run.id,
                    IncidentOccurrenceRecord.test_execution_id == execution.id,
                    IncidentOccurrenceRecord.occurrence_type == "failure",
                )
            )
        if incident.datahub_incident_urn is None:
            return "raise"
        if occurrence and occurrence.evidence_json.get("previous_status") == "resolved":
            return "reopen"
        return "update"

    async def _write_failure(
        self,
        client: IncidentClient,
        run: RunRecord,
        incident: IncidentRecord,
        operation: str,
    ) -> None:
        marker = f"histograph:{incident.id}"
        description = (
            f"{incident.summary}\n\n"
            f"Run: {self._public_app_url}/projects/{run.project_id}/runs/{run.id}\n"
            f"Ownership marker: {marker}"
        )
        writeback = await self._begin_writeback(
            run,
            incident,
            operation,
            {
                "resource_urn": incident.resource_urn,
                "title": incident.title,
                "description": description,
            },
        )
        if writeback.status == "succeeded":
            return
        try:
            datahub_urn = incident.datahub_incident_urn
            if operation == "raise":
                datahub_urn = await client.find_owned_active_incident(
                    resource_urn=incident.resource_urn,
                    ownership_marker=marker,
                )
                if datahub_urn is None:
                    datahub_urn = await client.raise_incident(
                        resource_urn=incident.resource_urn,
                        title=incident.title,
                        description=description,
                    )
            elif operation == "reopen":
                await client.reopen_incident(
                    incident_urn=datahub_urn,
                    message=f"Regression returned in Histograph run {run.id}",
                )
                await client.update_incident(
                    incident_urn=datahub_urn,
                    title=incident.title,
                    description=description,
                )
            else:
                await client.update_incident(
                    incident_urn=datahub_urn,
                    title=incident.title,
                    description=description,
                )
        except Exception as error:
            await self._finish_writeback(writeback.id, error=error)
            raise
        await self._finish_writeback(
            writeback.id,
            response={"incident_urn": datahub_urn},
            datahub_incident_urn=datahub_urn,
        )

    async def _record_success(
        self,
        run: RunRecord,
        project: ProjectRecord,
        execution: TestExecutionRecord,
        client: IncidentClient,
    ) -> None:
        policy = project.default_trigger_policy_json.get("datahub_writeback", {})
        threshold = policy.get("resolve_after_successes", 2) if isinstance(policy, dict) else 2
        threshold = min(max(int(threshold), 1), 20)
        async with self._session_factory() as session:
            incidents = tuple(
                await session.scalars(
                    select(IncidentRecord)
                    .where(
                        IncidentRecord.project_id == run.project_id,
                        IncidentRecord.protected_question_id == execution.protected_question_id,
                        IncidentRecord.status == IncidentStatus.OPEN,
                    )
                    .with_for_update()
                )
            )
            pending_resolution: list[IncidentRecord] = []
            for incident in incidents:
                occurrence = await session.scalar(
                    select(IncidentOccurrenceRecord).where(
                        IncidentOccurrenceRecord.incident_id == incident.id,
                        IncidentOccurrenceRecord.run_id == run.id,
                        IncidentOccurrenceRecord.test_execution_id == execution.id,
                        IncidentOccurrenceRecord.occurrence_type == "success",
                    )
                )
                if occurrence:
                    if incident.consecutive_success_count >= threshold:
                        pending_resolution.append(incident)
                    continue
                session.add(
                    IncidentOccurrenceRecord(
                        organization_id=run.organization_id,
                        project_id=run.project_id,
                        incident_id=incident.id,
                        run_id=run.id,
                        test_execution_id=execution.id,
                        occurrence_type="success",
                        evidence_json={"status": execution.status.value},
                    )
                )
                incident.consecutive_success_count += 1
                if incident.consecutive_success_count >= threshold:
                    pending_resolution.append(incident)
            await session.commit()
        for incident in pending_resolution:
            await self._resolve_incident(client, run, incident)

    async def _resolve_incident(
        self,
        client: IncidentClient,
        run: RunRecord,
        incident: IncidentRecord,
    ) -> None:
        if incident.datahub_incident_urn:
            writeback = await self._begin_writeback(
                run,
                incident,
                "resolve",
                {"incident_urn": incident.datahub_incident_urn},
            )
            if writeback.status != "succeeded":
                try:
                    await client.resolve_incident(
                        incident_urn=incident.datahub_incident_urn,
                        message=f"Verified by Histograph run {run.id}",
                    )
                except Exception as error:
                    await self._finish_writeback(writeback.id, error=error)
                    raise
                await self._finish_writeback(
                    writeback.id,
                    response={"incident_urn": incident.datahub_incident_urn},
                )
        async with self._session_factory() as session:
            stored = await session.get(IncidentRecord, incident.id, with_for_update=True)
            if stored and stored.status is IncidentStatus.OPEN:
                stored.status = IncidentStatus.RESOLVED
                stored.resolved_at = datetime.now(UTC)
                session.add(
                    AuditEventRecord(
                        organization_id=run.organization_id,
                        project_id=run.project_id,
                        actor_type="worker",
                        actor_id="histograph-incident-manager",
                        action="incident.resolved",
                        target_type="incident",
                        target_id=stored.id,
                        request_id=run.id,
                        details_json={"run_id": run.id},
                    )
                )
                await session.commit()

    async def _begin_writeback(
        self,
        run: RunRecord,
        incident: IncidentRecord,
        operation: str,
        request_json: dict,
    ) -> DataHubWritebackRecord:
        key = f"incident:{operation}:{incident.id}:{run.id}"
        async with self._session_factory() as session:
            writeback = await session.scalar(
                select(DataHubWritebackRecord)
                .where(
                    DataHubWritebackRecord.organization_id == run.organization_id,
                    DataHubWritebackRecord.idempotency_key == key,
                )
                .with_for_update()
            )
            if writeback is None:
                writeback = DataHubWritebackRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    incident_id=incident.id,
                    run_id=run.id,
                    idempotency_key=key,
                    operation=operation,
                    status="pending",
                    request_json=request_json,
                    attempt_count=0,
                )
                session.add(writeback)
                await session.flush()
            if writeback.status != "succeeded":
                writeback.status = "in_progress"
                writeback.attempt_count += 1
                writeback.last_error = None
                await session.commit()
            return writeback

    async def _finish_writeback(
        self,
        writeback_id: str,
        *,
        response: dict | None = None,
        error: Exception | None = None,
        datahub_incident_urn: str | None = None,
    ) -> None:
        async with self._session_factory() as session:
            writeback = await session.get(
                DataHubWritebackRecord, writeback_id, with_for_update=True
            )
            if writeback is None:
                raise RuntimeError("DataHub writeback record disappeared")
            if error:
                writeback.status = "failed"
                writeback.last_error = str(error)[:4000]
            else:
                writeback.status = "succeeded"
                writeback.response_json = response or {}
                writeback.last_error = None
                if datahub_incident_urn and writeback.incident_id:
                    incident = await session.get(IncidentRecord, writeback.incident_id)
                    if incident:
                        incident.datahub_incident_urn = datahub_incident_urn
            await session.commit()

    async def _execution_assets(self, execution: TestExecutionRecord) -> tuple[str, ...]:
        async with self._session_factory() as session:
            dependencies = ()
            if execution.baseline_version_id:
                dependencies = tuple(
                    await session.scalars(
                        select(BaselineDependencyRecord).where(
                            BaselineDependencyRecord.baseline_version_id
                            == execution.baseline_version_id
                        )
                    )
                )
        assets = [item.asset_urn for item in dependencies if _supports_incidents(item.asset_urn)]
        evidence = execution.evidence_json or {}
        assets.extend(
            item
            for item in evidence.get("selected_asset_urns", [])
            if isinstance(item, str) and _supports_incidents(item)
        )
        return tuple(dict.fromkeys(assets))


def _supports_incidents(asset_urn: str) -> bool:
    return asset_urn.startswith("urn:li:dataset:")


def _failed_finding_codes(execution: TestExecutionRecord) -> tuple[str, ...]:
    evaluation = execution.evaluation_json or {}
    codes = [
        finding.get("code")
        for finding in evaluation.get("findings", [])
        if isinstance(finding, dict)
        and finding.get("passed") is False
        and isinstance(finding.get("code"), str)
    ]
    if execution.error_code:
        codes.append(execution.error_code)
    return tuple(sorted(set(codes))) or ("agent_regression",)


def _failure_summary(finding_codes: tuple[str, ...]) -> str:
    return f"Histograph detected failed agent checks: {', '.join(finding_codes)}"
