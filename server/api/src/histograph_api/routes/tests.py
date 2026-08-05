from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from histograph_security import stable_fingerprint
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph_api.database.models import (
    AgentTargetRecord,
    BaselineDependencyRecord,
    BaselineVersionRecord,
    DataHubConnectionRecord,
    ProtectedQuestionRecord,
    ReviewDecisionRecord,
    RunRecord,
    TestExecutionRecord,
    TestSuiteRecord,
    TestVersionRecord,
)
from histograph_api.database.models.common import (
    BaselineStatus,
    ConnectionStatus,
    ExecutionStatus,
    Role,
    RunStatus,
    TriggerType,
)
from histograph_api.database.session import get_session
from histograph_api.schemas import (
    ApproveBaselineRequest,
    BaselineResponse,
    CreateBaselineRequest,
    CreateProtectedQuestionRequest,
    CreateTestSuiteRequest,
    ProtectedQuestionResponse,
    RunResponse,
    TestSuiteResponse,
    TestVersionResponse,
)
from histograph_api.security import Actor, get_actor
from histograph_api.security.authorization import authorize_project
from histograph_api.services.audit import add_audit_event
from histograph_api.services.orchestration import Orchestrator
from histograph_api.services.requests import request_id, source_ip

router = APIRouter(prefix="/projects/{project_id}", tags=["tests"])


@router.get("/test-suites", response_model=tuple[TestSuiteResponse, ...])
async def list_test_suites(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[TestSuiteRecord, ...]:
    await authorize_project(session, actor, project_id)
    suites = await session.scalars(
        select(TestSuiteRecord)
        .where(TestSuiteRecord.project_id == project_id, TestSuiteRecord.deleted_at.is_(None))
        .order_by(TestSuiteRecord.name)
    )
    return tuple(suites)


@router.get(
    "/protected-questions",
    response_model=tuple[ProtectedQuestionResponse, ...],
)
async def list_project_protected_questions(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[ProtectedQuestionRecord, ...]:
    await authorize_project(session, actor, project_id)
    questions = await session.scalars(
        select(ProtectedQuestionRecord)
        .where(
            ProtectedQuestionRecord.project_id == project_id,
            ProtectedQuestionRecord.deleted_at.is_(None),
        )
        .order_by(ProtectedQuestionRecord.name)
    )
    return tuple(questions)


@router.post("/test-suites", response_model=TestSuiteResponse, status_code=status.HTTP_201_CREATED)
async def create_test_suite(
    project_id: str,
    body: CreateTestSuiteRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TestSuiteRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER}
    )
    suite = TestSuiteRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        name=body.name,
        slug=body.slug,
        description=body.description,
    )
    session.add(suite)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="test_suite.created",
            target_type="test_suite",
            target_id=suite.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={"name": suite.name, "slug": suite.slug},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Test suite slug already exists") from error
    await session.refresh(suite)
    return suite


@router.get(
    "/test-suites/{suite_id}/protected-questions",
    response_model=tuple[ProtectedQuestionResponse, ...],
)
async def list_protected_questions(
    project_id: str,
    suite_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[ProtectedQuestionRecord, ...]:
    await authorize_project(session, actor, project_id)
    await _suite(session, project_id, suite_id)
    questions = await session.scalars(
        select(ProtectedQuestionRecord)
        .where(
            ProtectedQuestionRecord.project_id == project_id,
            ProtectedQuestionRecord.suite_id == suite_id,
            ProtectedQuestionRecord.deleted_at.is_(None),
        )
        .order_by(ProtectedQuestionRecord.name)
    )
    return tuple(questions)


@router.post(
    "/test-suites/{suite_id}/protected-questions",
    response_model=ProtectedQuestionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_protected_question(
    project_id: str,
    suite_id: str,
    body: CreateProtectedQuestionRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProtectedQuestionRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER, Role.AGENT_OWNER}
    )
    await _suite(session, project_id, suite_id)
    target = await session.scalar(
        select(AgentTargetRecord).where(
            AgentTargetRecord.id == body.agent_target_id,
            AgentTargetRecord.project_id == project_id,
            AgentTargetRecord.deleted_at.is_(None),
            AgentTargetRecord.active.is_(True),
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Agent target not found")
    configuration = _test_configuration(body)
    question = ProtectedQuestionRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        suite_id=suite_id,
        stable_key=body.stable_key,
        name=body.name,
        description=body.description,
        criticality=body.criticality,
        owner_reference=body.owner_reference,
        active=True,
    )
    session.add(question)
    try:
        await session.flush()
        version = TestVersionRecord(
            organization_id=project.organization_id,
            project_id=project_id,
            protected_question_id=question.id,
            agent_target_id=body.agent_target_id,
            version=1,
            configuration_json=configuration,
            fingerprint=stable_fingerprint(configuration),
            created_by=actor.subject,
        )
        session.add(version)
        await session.flush()
        question.active_version_id = version.id
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="protected_question.created",
            target_type="protected_question",
            target_id=question.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={
                "stable_key": question.stable_key,
                "test_version": version.version,
                "test_fingerprint": version.fingerprint,
            },
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(
            status_code=409, detail="Protected question key already exists"
        ) from error
    await session.refresh(question)
    return question


@router.get(
    "/protected-questions/{question_id}/versions",
    response_model=tuple[TestVersionResponse, ...],
)
async def list_test_versions(
    project_id: str,
    question_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[TestVersionRecord, ...]:
    await authorize_project(session, actor, project_id)
    await _question(session, project_id, question_id)
    versions = await session.scalars(
        select(TestVersionRecord)
        .where(TestVersionRecord.protected_question_id == question_id)
        .order_by(TestVersionRecord.version.desc())
    )
    return tuple(versions)


@router.post(
    "/protected-questions/{question_id}/baselines",
    response_model=BaselineResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_baseline(
    project_id: str,
    question_id: str,
    body: CreateBaselineRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BaselineVersionRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER, Role.REVIEWER}
    )
    await _question(session, project_id, question_id)
    test_version = await session.scalar(
        select(TestVersionRecord).where(
            TestVersionRecord.id == body.test_version_id,
            TestVersionRecord.protected_question_id == question_id,
        )
    )
    if test_version is None:
        raise HTTPException(status_code=404, detail="Test version not found")
    if body.source_execution_id:
        source_execution = await session.scalar(
            select(TestExecutionRecord).where(
                TestExecutionRecord.id == body.source_execution_id,
                TestExecutionRecord.project_id == project_id,
                TestExecutionRecord.protected_question_id == question_id,
                TestExecutionRecord.test_version_id == test_version.id,
                TestExecutionRecord.status == ExecutionStatus.PASSED,
            )
        )
        if source_execution is None:
            raise HTTPException(
                status_code=409,
                detail="Baseline source must be a passed execution of this test version",
            )
    current_version = await session.scalar(
        select(func.max(BaselineVersionRecord.version)).where(
            BaselineVersionRecord.protected_question_id == question_id
        )
    )
    baseline = BaselineVersionRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        protected_question_id=question_id,
        test_version_id=test_version.id,
        source_execution_id=body.source_execution_id,
        version=(current_version or 0) + 1,
        status=BaselineStatus.DRAFT,
        evidence_json=body.evidence,
        assertions_json=body.assertions,
        environment_fingerprint=body.environment_fingerprint,
    )
    session.add(baseline)
    await session.flush()
    for dependency in body.dependencies:
        session.add(
            BaselineDependencyRecord(
                organization_id=project.organization_id,
                project_id=project_id,
                baseline_version_id=baseline.id,
                asset_urn=dependency.asset_urn,
                field_path=dependency.field_path,
                dependency_type=dependency.dependency_type,
                environment=project.environment.value,
                evidence_json=dependency.evidence,
            )
        )
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project_id,
        action="baseline.created",
        target_type="baseline",
        target_id=baseline.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        after=_baseline_fingerprint_payload(baseline),
        details={"dependency_count": len(body.dependencies)},
    )
    await session.commit()
    await session.refresh(baseline)
    return baseline


@router.get(
    "/protected-questions/{question_id}/baselines",
    response_model=tuple[BaselineResponse, ...],
)
async def list_baselines(
    project_id: str,
    question_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[BaselineVersionRecord, ...]:
    await authorize_project(session, actor, project_id)
    await _question(session, project_id, question_id)
    baselines = await session.scalars(
        select(BaselineVersionRecord)
        .where(BaselineVersionRecord.protected_question_id == question_id)
        .order_by(BaselineVersionRecord.version.desc())
    )
    return tuple(baselines)


@router.post(
    "/protected-questions/{question_id}/baseline-runs",
    response_model=RunResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def capture_baseline(
    project_id: str,
    question_id: str,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=255)],
) -> RunRecord:
    project = await authorize_project(
        session,
        actor,
        project_id,
        {Role.OWNER, Role.ADMIN, Role.ENGINEER, Role.AGENT_OWNER, Role.REVIEWER},
    )
    question = await _question(session, project_id, question_id)
    existing = await session.scalar(
        select(RunRecord).where(
            RunRecord.organization_id == project.organization_id,
            RunRecord.project_id == project_id,
            RunRecord.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    if not question.active_version_id:
        raise HTTPException(status_code=409, detail="Protected question has no active test version")
    version = await session.get(TestVersionRecord, question.active_version_id)
    if version is None:
        raise HTTPException(
            status_code=409, detail="Protected question test version is unavailable"
        )
    target = await session.get(AgentTargetRecord, version.agent_target_id)
    if target is None or target.status is not ConnectionStatus.READY:
        raise HTTPException(status_code=409, detail="Protected question agent target is not ready")
    connection = await session.scalar(
        select(DataHubConnectionRecord).where(
            DataHubConnectionRecord.project_id == project_id,
            DataHubConnectionRecord.active.is_(True),
            DataHubConnectionRecord.status == ConnectionStatus.READY,
            DataHubConnectionRecord.deleted_at.is_(None),
        )
    )
    if connection is None:
        raise HTTPException(status_code=409, detail="Project DataHub connection is not ready")
    selection = {
        "suite_ids": [],
        "test_ids": [question.id],
        "asset_urns": [],
        "all_active": False,
        "baseline_capture": True,
    }
    run = RunRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        trigger_type=TriggerType.MANUAL,
        trigger_reference=f"baseline:{question.id}",
        idempotency_key=idempotency_key,
        requested_by=actor.subject,
        status=RunStatus.QUEUED,
        configuration_fingerprint=stable_fingerprint(
            {
                "project_id": project_id,
                "question_id": question.id,
                "test_version_id": version.id,
                "datahub_connection_id": connection.id,
                "datahub_connection_version": connection.version,
            }
        ),
        selection_json=selection,
        queued_at=datetime.now(UTC),
    )
    session.add(run)
    try:
        await session.flush()
        run.workflow_id = f"histograph/run/{run.id}"
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="baseline.capture_queued",
            target_type="run",
            target_id=run.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={"question_id": question.id, "test_version_id": version.id},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        duplicate = await session.scalar(
            select(RunRecord).where(
                RunRecord.organization_id == project.organization_id,
                RunRecord.project_id == project_id,
                RunRecord.idempotency_key == idempotency_key,
            )
        )
        if duplicate:
            return duplicate
        raise HTTPException(status_code=409, detail="Baseline run could not be queued") from error
    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        await orchestrator.start_run(run.id)
    except Exception as error:
        run.status = RunStatus.ERROR
        run.error_code = "workflow_start_failed"
        run.error_message = str(error)[:4000]
        run.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(status_code=503, detail="Workflow orchestrator unavailable") from error
    await session.refresh(run)
    return run


@router.post(
    "/protected-questions/{question_id}/baselines/{baseline_id}/approve",
    response_model=BaselineResponse,
)
async def approve_baseline(
    project_id: str,
    question_id: str,
    baseline_id: str,
    body: ApproveBaselineRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> BaselineVersionRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.REVIEWER}
    )
    question = await session.scalar(
        select(ProtectedQuestionRecord)
        .where(
            ProtectedQuestionRecord.id == question_id,
            ProtectedQuestionRecord.project_id == project_id,
            ProtectedQuestionRecord.deleted_at.is_(None),
        )
        .with_for_update()
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    baseline = await session.scalar(
        select(BaselineVersionRecord)
        .where(
            BaselineVersionRecord.id == baseline_id,
            BaselineVersionRecord.protected_question_id == question_id,
        )
        .with_for_update()
    )
    if baseline is None:
        raise HTTPException(status_code=404, detail="Baseline not found")
    if baseline.status is not BaselineStatus.DRAFT:
        raise HTTPException(status_code=409, detail="Only draft baselines can be approved")
    previous = None
    if question.active_baseline_id:
        previous = await session.get(BaselineVersionRecord, question.active_baseline_id)
        if previous:
            previous.status = BaselineStatus.SUPERSEDED
    now = datetime.now(UTC)
    baseline.status = BaselineStatus.APPROVED
    baseline.approved_by = actor.subject
    baseline.approved_at = now
    baseline.approval_justification = body.justification
    question.active_baseline_id = baseline.id
    after_fingerprint = stable_fingerprint(_baseline_fingerprint_payload(baseline))
    session.add(
        ReviewDecisionRecord(
            organization_id=project.organization_id,
            project_id=project_id,
            baseline_version_id=baseline.id,
            reviewer_reference=actor.subject,
            decision="approved",
            justification=body.justification,
            before_fingerprint=(
                stable_fingerprint(_baseline_fingerprint_payload(previous)) if previous else None
            ),
            after_fingerprint=after_fingerprint,
        )
    )
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project_id,
        action="baseline.approved",
        target_type="baseline",
        target_id=baseline.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        before=_baseline_fingerprint_payload(previous) if previous else None,
        after=_baseline_fingerprint_payload(baseline),
        details={"justification": body.justification},
    )
    await session.commit()
    await session.refresh(baseline)
    return baseline


async def _suite(session: AsyncSession, project_id: str, suite_id: str) -> TestSuiteRecord:
    suite = await session.scalar(
        select(TestSuiteRecord).where(
            TestSuiteRecord.id == suite_id,
            TestSuiteRecord.project_id == project_id,
            TestSuiteRecord.deleted_at.is_(None),
        )
    )
    if suite is None:
        raise HTTPException(status_code=404, detail="Test suite not found")
    return suite


async def _question(
    session: AsyncSession, project_id: str, question_id: str
) -> ProtectedQuestionRecord:
    question = await session.scalar(
        select(ProtectedQuestionRecord).where(
            ProtectedQuestionRecord.id == question_id,
            ProtectedQuestionRecord.project_id == project_id,
            ProtectedQuestionRecord.deleted_at.is_(None),
        )
    )
    if question is None:
        raise HTTPException(status_code=404, detail="Protected question not found")
    return question


def _test_configuration(body: CreateProtectedQuestionRequest) -> dict:
    return {
        "question": body.question,
        "context_query": body.context_query,
        "time_anchor": body.time_anchor,
        "assets": body.assets.model_dump(mode="json"),
        "sql": body.sql.model_dump(mode="json"),
        "result": body.result.model_dump(mode="json"),
        "response": body.response.model_dump(mode="json"),
        "stability": body.stability,
        "limits": body.limits,
        "tags": list(body.tags),
    }


def _baseline_fingerprint_payload(baseline: BaselineVersionRecord | None) -> dict:
    if baseline is None:
        return {}
    return {
        "test_version_id": baseline.test_version_id,
        "evidence": baseline.evidence_json,
        "assertions": baseline.assertions_json,
        "environment_fingerprint": baseline.environment_fingerprint,
        "status": baseline.status.value,
        "version": baseline.version,
    }
