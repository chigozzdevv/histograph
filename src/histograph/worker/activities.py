import asyncio
from contextlib import suppress
from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from temporalio import activity
from temporalio.exceptions import is_cancelled_exception

from histograph.api.database.models import (
    AgentEventRecord,
    AgentTargetRecord,
    ArtifactReferenceRecord,
    AuditEventRecord,
    BaselineDependencyRecord,
    BaselineVersionRecord,
    DataHubConnectionRecord,
    ExecutionAttemptRecord,
    ImpactPlanRecord,
    MetadataEventReceiptRecord,
    ProjectRecord,
    ProtectedQuestionRecord,
    RunRecord,
    RunTestSelectionRecord,
    ScheduleRecord,
    TestExecutionRecord,
    TestVersionRecord,
    WebhookReceiptRecord,
)
from histograph.api.database.models.common import (
    ArtifactKind,
    BaselineStatus,
    ConnectionStatus,
    ExecutionStatus,
    ReceiptStatus,
    RunStatus,
    SecretLocation,
    TriggerType,
)
from histograph.datahub import DataHubMcpClient
from histograph.domain import (
    AnalyticsAgentTarget,
    DataHubConnection,
    RunRequest,
    TestCase,
)
from histograph.github import GitHubAppClient
from histograph.runner import Runner
from histograph.security import EnvelopeCipher, stable_fingerprint
from histograph.storage import ArtifactStore
from histograph.worker.incidents import IncidentManager
from histograph.workflows import (
    CreateScheduledRunInput,
    ExecutionSummary,
    PlanResult,
    RunWorkflowInput,
)

_TERMINAL_EXECUTION_STATUSES = {
    ExecutionStatus.PASSED,
    ExecutionStatus.FAILED,
    ExecutionStatus.ERROR,
    ExecutionStatus.CANCELLED,
    ExecutionStatus.TIMED_OUT,
}


class RunActivities:
    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        cipher: EnvelopeCipher,
        artifact_store: ArtifactStore,
        runner: Runner | None = None,
        github_client: GitHubAppClient | None = None,
        incident_manager: IncidentManager | None = None,
    ):
        self._session_factory = session_factory
        self._cipher = cipher
        self._artifact_store = artifact_store
        self._runner = runner or Runner()
        self._github_client = github_client
        self._incident_manager = incident_manager

    @activity.defn(name="plan_run")
    async def plan_run(self, request: RunWorkflowInput) -> PlanResult:
        existing_result: PlanResult | None = None
        existing_run: RunRecord | None = None
        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            if run.status is RunStatus.ACTION_REQUIRED:
                count = await _selected_count(session, run.id)
                existing_result = PlanResult(action_required=True, selected_test_count=count)
                existing_run = run
            existing = await session.scalar(
                select(ImpactPlanRecord).where(ImpactPlanRecord.run_id == run.id)
            )
            if existing and existing_result is None:
                count = await _selected_count(session, run.id)
                existing_result = PlanResult(action_required=False, selected_test_count=count)
                existing_run = run
            if existing_result is None:
                run.status = RunStatus.PLANNING
                run.planned_at = datetime.now(UTC)
                await session.commit()

        if existing_result is not None and existing_run is not None:
            await self._update_github_plan(existing_run, existing_result)
            return existing_result

        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            questions = await self._active_questions(session, run.project_id)
            selected_ids, evidence, unknowns = await self._select_questions(session, run, questions)
            selections = []
            for question in questions:
                selected = question.id in selected_ids
                reason = (
                    "Protected question is affected by the requested change"
                    if selected
                    else "No dependency path connected this question to the requested change"
                )
                selection = RunTestSelectionRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    protected_question_id=question.id,
                    selected=selected,
                    reason=reason,
                    evidence_json=evidence.get(question.id, {}),
                )
                session.add(selection)
                selections.append(selection)
            selected_questions = [question for question in questions if question.id in selected_ids]
            missing_configuration = [
                question.stable_key
                for question in selected_questions
                if not question.active_version_id
                or (
                    not run.selection_json.get("baseline_capture")
                    and not question.active_baseline_id
                )
            ]
            unknowns.extend(
                f"Protected question {stable_key} has no approved executable baseline"
                for stable_key in missing_configuration
            )
            action_required = bool(unknowns) or not selected_questions
            risk_level = _risk_level(selected_questions)
            plan = {
                "changed_asset_urns": run.selection_json.get("asset_urns", []),
                "selected_test_ids": [question.id for question in selected_questions],
                "excluded_test_ids": [
                    question.id for question in questions if question.id not in selected_ids
                ],
                "unknowns": unknowns,
                "risk_level": risk_level,
                "selection_policy_version": "lineage-baseline-v1",
            }
            session.add(
                ImpactPlanRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    risk_level=risk_level,
                    plan_json=plan,
                    selection_policy_version="lineage-baseline-v1",
                )
            )
            run.impact_plan_json = plan
            run.status = RunStatus.ACTION_REQUIRED if action_required else RunStatus.EXECUTING
            if action_required:
                run.error_code = "impact_plan_action_required"
                run.error_message = "; ".join(unknowns) or "No protected questions were selected"
                await _mark_receipts_processed(session, run.id)
            await session.commit()
            result = PlanResult(
                action_required=action_required,
                selected_test_count=len(selected_questions),
            )
        await self._update_github_plan(run, result)
        return result

    @activity.defn(name="execute_selected_tests")
    async def execute_selected_tests(self, request: RunWorkflowInput) -> ExecutionSummary:
        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            run.status = RunStatus.EXECUTING
            run.started_at = run.started_at or datetime.now(UTC)
            selected = tuple(
                await session.scalars(
                    select(RunTestSelectionRecord)
                    .where(
                        RunTestSelectionRecord.run_id == run.id,
                        RunTestSelectionRecord.selected.is_(True),
                    )
                    .order_by(RunTestSelectionRecord.created_at)
                )
            )
            await session.commit()
        counts = {"passed": 0, "failed": 0, "warnings": 0, "errors": 0}
        for index, selection in enumerate(selected):
            status = await self._execute_test(request.run_id, selection.protected_question_id)
            if status is ExecutionStatus.PASSED:
                counts["passed"] += 1
            elif status is ExecutionStatus.FAILED:
                counts["failed"] += 1
            else:
                counts["errors"] += 1
            activity.heartbeat({"completed": index + 1, "total": len(selected)})
        return ExecutionSummary(**counts)

    @activity.defn(name="report_run")
    async def report_run(self, request: RunWorkflowInput, summary: ExecutionSummary) -> None:
        already_completed = False
        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            if (
                run.status
                in {
                    RunStatus.PASSED,
                    RunStatus.FAILED,
                    RunStatus.WARNING,
                    RunStatus.ERROR,
                }
                and run.report_json
            ):
                already_completed = True
            if not already_completed:
                run.status = RunStatus.REPORTING
                await session.flush()
                terminal_status = RunStatus.PASSED
                if summary.errors:
                    terminal_status = RunStatus.ERROR
                elif summary.failed:
                    terminal_status = RunStatus.FAILED
                elif summary.warnings:
                    terminal_status = RunStatus.WARNING
                report = {
                    "passed": summary.passed,
                    "failed": summary.failed,
                    "warnings": summary.warnings,
                    "errors": summary.errors,
                    "status": terminal_status.value,
                }
                artifact = await self._artifact_store.put_json(
                    _artifact_key(run, "report.json"), report
                )
                session.add(
                    ArtifactReferenceRecord(
                        organization_id=run.organization_id,
                        project_id=run.project_id,
                        run_id=run.id,
                        kind=ArtifactKind.REPORT,
                        object_key=artifact.object_key,
                        sha256=artifact.sha256,
                        content_type=artifact.content_type,
                        size_bytes=artifact.size_bytes,
                    )
                )
                run.report_json = report
                run.status = terminal_status
                run.completed_at = datetime.now(UTC)
                receipt = await session.scalar(
                    select(MetadataEventReceiptRecord).where(
                        MetadataEventReceiptRecord.run_id == run.id
                    )
                )
                if receipt:
                    receipt.status = ReceiptStatus.PROCESSED
                    receipt.processed_at = datetime.now(UTC)
                webhook_receipt = await session.scalar(
                    select(WebhookReceiptRecord).where(WebhookReceiptRecord.run_id == run.id)
                )
                if webhook_receipt:
                    webhook_receipt.status = ReceiptStatus.PROCESSED
                    webhook_receipt.processed_at = datetime.now(UTC)
                await session.commit()
        await self._propose_baselines(run.id)
        await self._update_github_report(run)
        if self._incident_manager:
            await self._incident_manager.process_run(run.id)

    @activity.defn(name="cancel_run")
    async def cancel_run(self, request: RunWorkflowInput) -> None:
        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            if run.status not in {
                RunStatus.PASSED,
                RunStatus.FAILED,
                RunStatus.WARNING,
                RunStatus.ERROR,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                run.status = RunStatus.CANCELLED
                run.completed_at = datetime.now(UTC)
                await session.commit()
        await self._update_github_cancelled(run)

    @activity.defn(name="fail_run")
    async def fail_run(
        self,
        request: RunWorkflowInput,
        failure_type: str,
        failure_message: str,
    ) -> None:
        async with self._session_factory() as session:
            run = await _run_for_update(session, request.run_id)
            if run.status not in {
                RunStatus.PASSED,
                RunStatus.FAILED,
                RunStatus.WARNING,
                RunStatus.ERROR,
                RunStatus.CANCELLED,
                RunStatus.TIMED_OUT,
            }:
                run.status = RunStatus.ERROR
                run.error_code = "workflow_failed"
                run.error_message = f"{failure_type}: {failure_message}"[:4000]
                run.completed_at = datetime.now(UTC)
                await _mark_receipts_failed(session, run.id, run.error_message)
                await session.commit()
        await self._update_github_report(run)

    @activity.defn(name="create_scheduled_run")
    async def create_scheduled_run(self, request: CreateScheduledRunInput) -> str:
        async with self._session_factory() as session:
            schedule = await session.scalar(
                select(ScheduleRecord).where(
                    ScheduleRecord.id == request.schedule_id,
                    ScheduleRecord.active.is_(True),
                )
            )
            if schedule is None:
                raise ValueError("Schedule is inactive or unavailable")
            idempotency_key = f"schedule:{schedule.id}:{request.workflow_run_id}"
            existing = await session.scalar(
                select(RunRecord).where(
                    RunRecord.organization_id == schedule.organization_id,
                    RunRecord.project_id == schedule.project_id,
                    RunRecord.idempotency_key == idempotency_key,
                )
            )
            if existing:
                return existing.id
            selection = {
                "suite_ids": [schedule.suite_id] if schedule.suite_id else [],
                "test_ids": (
                    [schedule.protected_question_id] if schedule.protected_question_id else []
                ),
                "asset_urns": [],
                "all_active": False,
            }
            run = RunRecord(
                organization_id=schedule.organization_id,
                project_id=schedule.project_id,
                trigger_type=TriggerType.SCHEDULE,
                trigger_reference=schedule.id,
                idempotency_key=idempotency_key,
                requested_by=f"schedule:{schedule.id}",
                status=RunStatus.QUEUED,
                workflow_id=None,
                configuration_fingerprint=stable_fingerprint(
                    {"schedule_id": schedule.id, "selection": selection}
                ),
                selection_json=selection,
                queued_at=datetime.now(UTC),
            )
            session.add(run)
            await session.flush()
            run.workflow_id = f"histograph/run/{run.id}"
            await session.commit()
            return run.id

    async def _active_questions(
        self, session: AsyncSession, project_id: str
    ) -> tuple[ProtectedQuestionRecord, ...]:
        questions = await session.scalars(
            select(ProtectedQuestionRecord)
            .where(
                ProtectedQuestionRecord.project_id == project_id,
                ProtectedQuestionRecord.active.is_(True),
                ProtectedQuestionRecord.deleted_at.is_(None),
            )
            .order_by(ProtectedQuestionRecord.id)
        )
        return tuple(questions)

    async def _select_questions(
        self,
        session: AsyncSession,
        run: RunRecord,
        questions: tuple[ProtectedQuestionRecord, ...],
    ) -> tuple[set[str], dict[str, dict], list[str]]:
        selection = run.selection_json
        selected: set[str] = set()
        evidence: dict[str, dict] = {}
        unknowns: list[str] = []
        if selection.get("all_active"):
            selected.update(question.id for question in questions)
        suite_ids = set(selection.get("suite_ids", []))
        selected.update(question.id for question in questions if question.suite_id in suite_ids)
        requested_ids = set(selection.get("test_ids", []))
        selected.update(question.id for question in questions if question.id in requested_ids)
        changed_assets = tuple(dict.fromkeys(selection.get("asset_urns", [])))
        if changed_assets:
            affected_assets, lineage_evidence, lineage_unknowns = await self._affected_assets(
                session, run, changed_assets
            )
            unknowns.extend(lineage_unknowns)
            dependencies = tuple(
                await session.scalars(
                    select(BaselineDependencyRecord).where(
                        BaselineDependencyRecord.project_id == run.project_id,
                        BaselineDependencyRecord.asset_urn.in_(affected_assets),
                    )
                )
            )
            question_by_baseline = {
                question.active_baseline_id: question
                for question in questions
                if question.active_baseline_id
            }
            for dependency in dependencies:
                question = question_by_baseline.get(dependency.baseline_version_id)
                if question is None:
                    continue
                selected.add(question.id)
                evidence.setdefault(question.id, {"matched_dependencies": []})[
                    "matched_dependencies"
                ].append(
                    {
                        "asset_urn": dependency.asset_urn,
                        "field_path": dependency.field_path,
                        "dependency_type": dependency.dependency_type,
                    }
                )
                evidence[question.id]["lineage"] = lineage_evidence
            if not dependencies:
                unknowns.append(
                    "No approved baseline dependency matched the changed asset or its "
                    "downstream lineage"
                )
        return selected, evidence, unknowns

    async def _affected_assets(
        self,
        session: AsyncSession,
        run: RunRecord,
        changed_assets: tuple[str, ...],
    ) -> tuple[set[str], list[dict], list[str]]:
        connection = await session.scalar(
            select(DataHubConnectionRecord).where(
                DataHubConnectionRecord.project_id == run.project_id,
                DataHubConnectionRecord.active.is_(True),
                DataHubConnectionRecord.deleted_at.is_(None),
            )
        )
        if connection is None:
            return set(changed_assets), [], ["Project has no active DataHub connection"]
        if connection.status is not ConnectionStatus.READY:
            return set(changed_assets), [], ["Active DataHub connection is not verified"]
        if connection.secret_location is SecretLocation.PRIVATE_RUNNER:
            return (
                set(changed_assets),
                [],
                ["Impact planning requires the configured private runner"],
            )
        if not connection.encrypted_credentials:
            return set(changed_assets), [], ["DataHub credentials are unavailable"]
        token = self._cipher.decrypt(
            connection.encrypted_credentials,
            context=_secret_context("datahub", run.project_id, connection.id),
        )
        client = DataHubMcpClient(DataHubConnection(mcp_url=connection.mcp_url, token=token))
        affected = set(changed_assets)
        evidence: list[dict] = []
        unknowns: list[str] = []
        for urn in changed_assets:
            try:
                results = await client.get_downstream_lineage(urn, max_hops=3, max_results=100)
            except Exception as error:
                unknowns.append(f"DataHub lineage lookup failed for {urn}: {error}")
                continue
            downstream = []
            for result in results:
                entity = result.get("entity", {})
                downstream_urn = entity.get("urn") if isinstance(entity, dict) else None
                if isinstance(downstream_urn, str):
                    affected.add(downstream_urn)
                    downstream.append(
                        {
                            "urn": downstream_urn,
                            "degree": result.get("degree"),
                            "lineage_columns": result.get("lineageColumns", []),
                        }
                    )
            evidence.append({"source_urn": urn, "downstream": downstream})
        return affected, evidence, unknowns

    async def _execute_test(self, run_id: str, protected_question_id: str) -> ExecutionStatus:
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(TestExecutionRecord).where(
                    TestExecutionRecord.run_id == run_id,
                    TestExecutionRecord.protected_question_id == protected_question_id,
                )
            )
            if existing and existing.status in _TERMINAL_EXECUTION_STATUSES:
                return existing.status
            run = await session.get(RunRecord, run_id)
            question = await session.get(ProtectedQuestionRecord, protected_question_id)
            if run is None or question is None or not question.active_version_id:
                return ExecutionStatus.ERROR
            version = await session.get(TestVersionRecord, question.active_version_id)
            if version is None:
                return ExecutionStatus.ERROR
            target = await session.get(AgentTargetRecord, version.agent_target_id)
            connection = await session.scalar(
                select(DataHubConnectionRecord).where(
                    DataHubConnectionRecord.project_id == run.project_id,
                    DataHubConnectionRecord.active.is_(True),
                    DataHubConnectionRecord.deleted_at.is_(None),
                )
            )
            if target is None or connection is None:
                return ExecutionStatus.ERROR
            execution = existing or TestExecutionRecord(
                organization_id=run.organization_id,
                project_id=run.project_id,
                run_id=run.id,
                protected_question_id=question.id,
                test_version_id=version.id,
                baseline_version_id=question.active_baseline_id,
                agent_target_id=target.id,
                status=ExecutionStatus.QUEUED,
                attempt_count=0,
                trace_id=str(uuid4()),
            )
            session.add(execution)
            await session.flush()
            execution.attempt_count += 1
            execution.status = ExecutionStatus.EXECUTING
            execution.started_at = execution.started_at or datetime.now(UTC)
            attempt = ExecutionAttemptRecord(
                organization_id=run.organization_id,
                project_id=run.project_id,
                test_execution_id=execution.id,
                attempt_number=execution.attempt_count,
                status=ExecutionStatus.EXECUTING,
                started_at=datetime.now(UTC),
            )
            session.add(attempt)
            await session.commit()
            execution_id = execution.id
        try:
            request = self._runner_request(run, question, version, target, connection)
            runner_task = asyncio.create_task(self._runner.execute(request, run_id=execution_id))
            heartbeat_task = asyncio.create_task(_heartbeat_execution(run_id, execution_id))
            try:
                done, _ = await asyncio.wait(
                    {runner_task, heartbeat_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
                if runner_task in done:
                    result = await runner_task
                else:
                    runner_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await runner_task
                    await heartbeat_task
                    raise RuntimeError("Execution heartbeat stopped unexpectedly")
            finally:
                heartbeat_task.cancel()
                with suppress(asyncio.CancelledError):
                    await heartbeat_task
        except Exception as error:
            if is_cancelled_exception(error):
                raise
            async with self._session_factory() as session:
                execution = await session.get(TestExecutionRecord, execution_id)
                attempt = await session.scalar(
                    select(ExecutionAttemptRecord).where(
                        ExecutionAttemptRecord.test_execution_id == execution_id,
                        ExecutionAttemptRecord.attempt_number == execution.attempt_count,
                    )
                )
                now = datetime.now(UTC)
                execution.status = ExecutionStatus.ERROR
                execution.error_code = "agent_execution_failed"
                execution.error_message = str(error)[:4000]
                execution.completed_at = now
                if attempt:
                    attempt.status = ExecutionStatus.ERROR
                    attempt.error_code = execution.error_code
                    attempt.error_message = execution.error_message
                    attempt.completed_at = now
                await session.commit()
            return ExecutionStatus.ERROR
        async with self._session_factory() as session:
            execution = await session.get(TestExecutionRecord, execution_id)
            run = await session.get(RunRecord, run_id)
            if execution is None or run is None:
                raise RuntimeError("Execution state was removed while the test was running")
            result_payload = result.model_dump(mode="json")
            artifact = await self._artifact_store.put_json(
                _artifact_key(run, f"executions/{execution.id}/evidence.json"),
                result_payload,
            )
            session.add(
                ArtifactReferenceRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    run_id=run.id,
                    test_execution_id=execution.id,
                    kind=ArtifactKind.AGENT_TRACE,
                    object_key=artifact.object_key,
                    sha256=artifact.sha256,
                    content_type=artifact.content_type,
                    size_bytes=artifact.size_bytes,
                )
            )
            for event in result.evidence.events:
                session.add(
                    AgentEventRecord(
                        organization_id=run.organization_id,
                        project_id=run.project_id,
                        test_execution_id=execution.id,
                        event_id=event.event_id,
                        sequence=event.sequence,
                        event_type=event.type.value,
                        trace_id=event.trace_id,
                        event_timestamp=event.timestamp,
                        payload_json=event.payload,
                    )
                )
            status = (
                ExecutionStatus.PASSED
                if result.status.value == "passed"
                else ExecutionStatus.FAILED
            )
            execution.status = status
            execution.evidence_json = {
                "artifact_key": artifact.object_key,
                "artifact_sha256": artifact.sha256,
                "selected_asset_urns": list(result.evidence.selected_asset_urns),
                "sql_execution_count": len(result.evidence.sql_executions),
                "event_count": len(result.evidence.events),
            }
            execution.evaluation_json = result.evaluation.model_dump(mode="json")
            execution.completed_at = result.completed_at
            attempt = await session.scalar(
                select(ExecutionAttemptRecord).where(
                    ExecutionAttemptRecord.test_execution_id == execution.id,
                    ExecutionAttemptRecord.attempt_number == execution.attempt_count,
                )
            )
            if attempt:
                attempt.status = status
                attempt.completed_at = result.completed_at
            await session.commit()
            return status

    async def _update_github_plan(self, run: RunRecord, result: PlanResult) -> None:
        context = _github_context(run)
        if self._github_client is None or context is None:
            return
        if result.action_required:
            unknowns = run.impact_plan_json.get("unknowns", []) if run.impact_plan_json else []
            summary = "\n".join(f"- {item}" for item in unknowns) or (
                "Histograph could not select an executable protected question."
            )
            await self._github_client.update_check_run(
                **context,
                status="completed",
                conclusion="action_required",
                title="Histograph needs configuration or review",
                summary=summary,
            )
            return
        await self._github_client.update_check_run(
            **context,
            status="in_progress",
            title=f"Running {result.selected_test_count} protected questions",
            summary="DataHub lineage and approved baselines selected the affected agent tests.",
        )

    async def _update_github_report(self, run: RunRecord) -> None:
        context = _github_context(run)
        if self._github_client is None or context is None:
            return
        conclusions = {
            RunStatus.PASSED: "success",
            RunStatus.FAILED: "failure",
            RunStatus.WARNING: "neutral",
            RunStatus.ERROR: "failure",
        }
        report = run.report_json or {}
        await self._github_client.update_check_run(
            **context,
            status="completed",
            conclusion=conclusions.get(run.status, "failure"),
            title=f"Histograph run {run.status.value}",
            summary=(
                f"Passed: {report.get('passed', 0)} · Failed: {report.get('failed', 0)} · "
                f"Warnings: {report.get('warnings', 0)} · Errors: {report.get('errors', 0)}"
            ),
        )

    async def _update_github_cancelled(self, run: RunRecord) -> None:
        context = _github_context(run)
        if self._github_client is None or context is None:
            return
        await self._github_client.update_check_run(
            **context,
            status="completed",
            conclusion="cancelled",
            title="Histograph run cancelled",
            summary="This run was cancelled or superseded by a newer commit.",
        )

    async def _propose_baselines(self, run_id: str) -> None:
        async with self._session_factory() as session:
            run = await session.get(RunRecord, run_id)
            if run is None or not run.selection_json.get("baseline_capture"):
                return
            project = await session.get(ProjectRecord, run.project_id)
            executions = tuple(
                await session.scalars(
                    select(TestExecutionRecord).where(
                        TestExecutionRecord.run_id == run.id,
                        TestExecutionRecord.status == ExecutionStatus.PASSED,
                    )
                )
            )
            draft_ids: list[str] = []
            for execution in executions:
                existing = await session.scalar(
                    select(BaselineVersionRecord).where(
                        BaselineVersionRecord.source_execution_id == execution.id
                    )
                )
                if existing:
                    draft_ids.append(existing.id)
                    continue
                version = await session.get(TestVersionRecord, execution.test_version_id)
                target = await session.get(AgentTargetRecord, execution.agent_target_id)
                if version is None or target is None or project is None:
                    raise RuntimeError("Baseline capture references unavailable configuration")
                current_version = await session.scalar(
                    select(BaselineVersionRecord.version)
                    .where(
                        BaselineVersionRecord.protected_question_id
                        == execution.protected_question_id
                    )
                    .order_by(BaselineVersionRecord.version.desc())
                    .limit(1)
                )
                configuration = version.configuration_json
                evidence = execution.evidence_json or {}
                assets = list(evidence.get("selected_asset_urns", []))
                assets.extend(configuration.get("assets", {}).get("required", []))
                asset_urns = tuple(
                    dict.fromkeys(
                        item
                        for item in assets
                        if isinstance(item, str) and item.startswith("urn:li:")
                    )
                )
                assertions = {
                    key: configuration.get(key, {})
                    for key in ("assets", "sql", "result", "response", "stability", "limits")
                }
                baseline = BaselineVersionRecord(
                    organization_id=run.organization_id,
                    project_id=run.project_id,
                    protected_question_id=execution.protected_question_id,
                    test_version_id=execution.test_version_id,
                    source_execution_id=execution.id,
                    version=(current_version or 0) + 1,
                    status=BaselineStatus.DRAFT,
                    evidence_json={
                        "run_id": run.id,
                        "execution_id": execution.id,
                        "agent_trace": evidence,
                        "evaluation": execution.evaluation_json or {},
                    },
                    assertions_json=assertions,
                    environment_fingerprint=stable_fingerprint(
                        {
                            "project_environment": project.environment.value,
                            "test_fingerprint": version.fingerprint,
                            "agent_target_id": target.id,
                            "agent_target_version": target.version,
                            "agent_prompt_fingerprint": target.prompt_fingerprint,
                            "agent_models": target.model_identifiers_json,
                        }
                    ),
                )
                session.add(baseline)
                await session.flush()
                for asset_urn in asset_urns:
                    session.add(
                        BaselineDependencyRecord(
                            organization_id=run.organization_id,
                            project_id=run.project_id,
                            baseline_version_id=baseline.id,
                            asset_urn=asset_urn,
                            field_path="",
                            dependency_type="agent_context",
                            environment=project.environment.value,
                            evidence_json={"source_execution_id": execution.id},
                        )
                    )
                session.add(
                    AuditEventRecord(
                        organization_id=run.organization_id,
                        project_id=run.project_id,
                        actor_type="worker",
                        actor_id="histograph-baseline-manager",
                        action="baseline.proposed",
                        target_type="baseline",
                        target_id=baseline.id,
                        request_id=run.id,
                        details_json={
                            "source_execution_id": execution.id,
                            "dependency_count": len(asset_urns),
                        },
                    )
                )
                draft_ids.append(baseline.id)
            if run.report_json is not None:
                run.report_json = {**run.report_json, "baseline_draft_ids": draft_ids}
            await session.commit()

    def _runner_request(
        self,
        run: RunRecord,
        question: ProtectedQuestionRecord,
        version: TestVersionRecord,
        target: AgentTargetRecord,
        connection: DataHubConnectionRecord,
    ) -> RunRequest:
        if connection.secret_location is not SecretLocation.MANAGED:
            raise ValueError("Managed worker cannot use private-runner DataHub credentials")
        if not connection.encrypted_credentials:
            raise ValueError("DataHub credentials are unavailable")
        datahub_token = self._cipher.decrypt(
            connection.encrypted_credentials,
            context=_secret_context("datahub", run.project_id, connection.id),
        )
        agent_token = None
        if target.encrypted_credentials:
            agent_token = self._cipher.decrypt(
                target.encrypted_credentials,
                context=_secret_context("agent", run.project_id, target.id),
            )
        configuration = version.configuration_json
        test_case = TestCase(
            id=question.stable_key,
            name=question.name,
            question=configuration["question"],
            context_query=configuration.get("context_query"),
            assets=configuration.get("assets", {}),
            sql=configuration.get("sql", {}),
            result=configuration.get("result", {}),
            response=configuration.get("response", {}),
        )
        return RunRequest(
            test_case=test_case,
            datahub=DataHubConnection(mcp_url=connection.mcp_url, token=datahub_token),
            agent=AnalyticsAgentTarget(
                base_url=target.base_url,
                engine_name=target.engine_name,
                token=agent_token,
            ),
        )


async def _run_for_update(session: AsyncSession, run_id: str) -> RunRecord:
    run = await session.scalar(select(RunRecord).where(RunRecord.id == run_id).with_for_update())
    if run is None:
        raise ValueError(f"Run {run_id} was not found")
    return run


async def _selected_count(session: AsyncSession, run_id: str) -> int:
    records = await session.scalars(
        select(RunTestSelectionRecord.id).where(
            RunTestSelectionRecord.run_id == run_id,
            RunTestSelectionRecord.selected.is_(True),
        )
    )
    return len(tuple(records))


async def _mark_receipts_processed(session: AsyncSession, run_id: str) -> None:
    now = datetime.now(UTC)
    metadata_receipt = await session.scalar(
        select(MetadataEventReceiptRecord).where(MetadataEventReceiptRecord.run_id == run_id)
    )
    if metadata_receipt:
        metadata_receipt.status = ReceiptStatus.PROCESSED
        metadata_receipt.processed_at = now
    webhook_receipt = await session.scalar(
        select(WebhookReceiptRecord).where(WebhookReceiptRecord.run_id == run_id)
    )
    if webhook_receipt:
        webhook_receipt.status = ReceiptStatus.PROCESSED
        webhook_receipt.processed_at = now


async def _mark_receipts_failed(session: AsyncSession, run_id: str, message: str) -> None:
    metadata_receipt = await session.scalar(
        select(MetadataEventReceiptRecord).where(MetadataEventReceiptRecord.run_id == run_id)
    )
    if metadata_receipt:
        metadata_receipt.status = ReceiptStatus.FAILED
        metadata_receipt.error_message = message
    webhook_receipt = await session.scalar(
        select(WebhookReceiptRecord).where(WebhookReceiptRecord.run_id == run_id)
    )
    if webhook_receipt:
        webhook_receipt.status = ReceiptStatus.FAILED
        webhook_receipt.error_message = message


async def _heartbeat_execution(run_id: str, execution_id: str) -> None:
    while True:
        activity.heartbeat({"run_id": run_id, "execution_id": execution_id})
        await asyncio.sleep(30)


def _risk_level(questions: list[ProtectedQuestionRecord]) -> str:
    criticalities = {question.criticality for question in questions}
    for level in ("critical", "high", "medium", "low"):
        if level in criticalities:
            return level
    return "unknown"


def _secret_context(kind: str, project_id: str, record_id: str) -> str:
    return f"histograph:{kind}:{project_id}:{record_id}"


def _artifact_key(run: RunRecord, suffix: str) -> str:
    return f"organizations/{run.organization_id}/projects/{run.project_id}/runs/{run.id}/{suffix}"


def _github_context(run: RunRecord) -> dict | None:
    value = run.selection_json.get("github")
    if not isinstance(value, dict):
        return None
    installation_id = value.get("installation_id")
    owner = value.get("owner")
    repository = value.get("repository")
    check_run_id = value.get("check_run_id")
    if not (
        isinstance(installation_id, int)
        and isinstance(owner, str)
        and isinstance(repository, str)
        and isinstance(check_run_id, int)
    ):
        return None
    return {
        "installation_id": installation_id,
        "owner": owner,
        "repository": repository,
        "check_run_id": check_run_id,
    }
