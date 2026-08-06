from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import (
    AgentEventRecord,
    DataHubConnectionRecord,
    ProtectedQuestionRecord,
    RunRecord,
    TestExecutionRecord,
    TestSuiteRecord,
)
from histograph.api.database.models.common import ConnectionStatus, Role, RunStatus, TriggerType
from histograph.api.database.session import get_session
from histograph.api.schemas import CreateRunRequest, RunEventResponse, RunListResponse, RunResponse
from histograph.api.security import Actor, get_actor
from histograph.api.security.authorization import authorize_project
from histograph.api.services.audit import add_audit_event
from histograph.api.services.orchestration import Orchestrator
from histograph.api.services.requests import request_id, source_ip
from histograph.security import stable_fingerprint

router = APIRouter(prefix="/projects/{project_id}/runs", tags=["runs"])


@router.get("", response_model=RunListResponse)
async def list_runs(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 50,
) -> RunListResponse:
    await authorize_project(session, actor, project_id)
    bounded_limit = min(max(limit, 1), 200)
    records = await session.scalars(
        select(RunRecord)
        .where(RunRecord.project_id == project_id)
        .order_by(RunRecord.created_at.desc())
        .limit(bounded_limit)
    )
    return RunListResponse(items=tuple(RunResponse.model_validate(record) for record in records))


@router.post("", response_model=RunResponse, status_code=status.HTTP_202_ACCEPTED)
async def create_run(
    project_id: str,
    body: CreateRunRequest,
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
    existing = await session.scalar(
        select(RunRecord).where(
            RunRecord.organization_id == project.organization_id,
            RunRecord.project_id == project_id,
            RunRecord.idempotency_key == idempotency_key,
        )
    )
    if existing:
        return existing
    await _validate_selection(session, project_id, body)
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
    selection = body.selection.model_dump(mode="json")
    queued_at = datetime.now(UTC)
    record = RunRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        trigger_type=TriggerType(body.trigger_type),
        trigger_reference=body.trigger_reference,
        idempotency_key=idempotency_key,
        requested_by=actor.subject,
        status=RunStatus.QUEUED,
        configuration_fingerprint=stable_fingerprint(
            {
                "project_id": project_id,
                "datahub_connection_id": connection.id,
                "datahub_connection_version": connection.version,
                "selection": selection,
            }
        ),
        selection_json=selection,
        queued_at=queued_at,
    )
    session.add(record)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="run.queued",
            target_type="run",
            target_id=record.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={
                "trigger_type": record.trigger_type.value,
                "selection": selection,
                "configuration_fingerprint": record.configuration_fingerprint,
            },
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
        raise HTTPException(status_code=409, detail="Run could not be queued") from error
    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        record.workflow_id = await orchestrator.start_run(record.id)
        await session.commit()
    except Exception as error:
        record.status = RunStatus.ERROR
        record.error_code = "workflow_start_failed"
        record.error_message = str(error)[:4000]
        record.completed_at = datetime.now(UTC)
        await session.commit()
        raise HTTPException(status_code=503, detail="Workflow orchestrator unavailable") from error
    await session.refresh(record)
    return record


@router.get("/{run_id}", response_model=RunResponse)
async def get_run(
    project_id: str,
    run_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunRecord:
    await authorize_project(session, actor, project_id)
    return await _run(session, project_id, run_id)


@router.get("/{run_id}/events", response_model=tuple[RunEventResponse, ...])
async def list_run_events(
    project_id: str,
    run_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[AgentEventRecord, ...]:
    await authorize_project(session, actor, project_id)
    await _run(session, project_id, run_id)
    events = await session.scalars(
        select(AgentEventRecord)
        .join(TestExecutionRecord, AgentEventRecord.test_execution_id == TestExecutionRecord.id)
        .where(TestExecutionRecord.run_id == run_id)
        .order_by(AgentEventRecord.created_at, AgentEventRecord.sequence)
    )
    return tuple(events)


@router.post("/{run_id}/cancel", response_model=RunResponse)
async def cancel_run(
    project_id: str,
    run_id: str,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> RunRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER, Role.AGENT_OWNER}
    )
    run = await _run(session, project_id, run_id)
    if run.status in {
        RunStatus.PASSED,
        RunStatus.FAILED,
        RunStatus.WARNING,
        RunStatus.ERROR,
        RunStatus.CANCELLED,
        RunStatus.TIMED_OUT,
    }:
        return run
    run.cancellation_requested_at = datetime.now(UTC)
    if run.workflow_id:
        orchestrator: Orchestrator = request.app.state.orchestrator
        await orchestrator.cancel_run(run.workflow_id)
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project_id,
        action="run.cancellation_requested",
        target_type="run",
        target_id=run.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
    )
    await session.commit()
    await session.refresh(run)
    return run


async def _validate_selection(
    session: AsyncSession, project_id: str, body: CreateRunRequest
) -> None:
    selection = body.selection
    if selection.suite_ids:
        found = set(
            await session.scalars(
                select(TestSuiteRecord.id).where(
                    TestSuiteRecord.project_id == project_id,
                    TestSuiteRecord.id.in_(selection.suite_ids),
                    TestSuiteRecord.deleted_at.is_(None),
                )
            )
        )
        if found != set(selection.suite_ids):
            raise HTTPException(status_code=404, detail="One or more test suites were not found")
    if selection.test_ids:
        found = set(
            await session.scalars(
                select(ProtectedQuestionRecord.id).where(
                    ProtectedQuestionRecord.project_id == project_id,
                    ProtectedQuestionRecord.id.in_(selection.test_ids),
                    ProtectedQuestionRecord.deleted_at.is_(None),
                )
            )
        )
        if found != set(selection.test_ids):
            raise HTTPException(
                status_code=404, detail="One or more protected questions were not found"
            )


async def _run(session: AsyncSession, project_id: str, run_id: str) -> RunRecord:
    record = await session.scalar(
        select(RunRecord).where(RunRecord.id == run_id, RunRecord.project_id == project_id)
    )
    if record is None:
        raise HTTPException(status_code=404, detail="Run not found")
    return record
