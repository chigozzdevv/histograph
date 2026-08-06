from datetime import UTC, datetime
from typing import Annotated
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from croniter import croniter
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import (
    DataHubConnectionRecord,
    MetadataEventReceiptRecord,
    ProtectedQuestionRecord,
    RunRecord,
    ScheduleRecord,
    TestSuiteRecord,
)
from histograph.api.database.models.common import (
    ReceiptStatus,
    Role,
    RunStatus,
    ScheduleConcurrency,
    TriggerType,
    new_id,
)
from histograph.api.database.session import get_session
from histograph.api.schemas import (
    CreateScheduleRequest,
    MetadataEventRequest,
    MetadataEventResponse,
    ScheduleResponse,
)
from histograph.api.security import Actor, ActorType, get_actor
from histograph.api.security.authorization import authorize_project
from histograph.api.services.audit import add_audit_event
from histograph.api.services.orchestration import Orchestrator
from histograph.api.services.requests import request_id, source_ip
from histograph.security import stable_fingerprint

router = APIRouter(prefix="/projects/{project_id}", tags=["triggers"])


@router.get("/schedules", response_model=tuple[ScheduleResponse, ...])
async def list_schedules(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[ScheduleRecord, ...]:
    await authorize_project(session, actor, project_id)
    schedules = await session.scalars(
        select(ScheduleRecord)
        .where(ScheduleRecord.project_id == project_id)
        .order_by(ScheduleRecord.name)
    )
    return tuple(schedules)


@router.post("/schedules", response_model=ScheduleResponse, status_code=status.HTTP_201_CREATED)
async def create_schedule(
    project_id: str,
    body: CreateScheduleRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ScheduleRecord:
    project = await authorize_project(
        session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER, Role.AGENT_OWNER}
    )
    _validate_schedule(body)
    if body.suite_id:
        suite = await session.scalar(
            select(TestSuiteRecord.id).where(
                TestSuiteRecord.id == body.suite_id,
                TestSuiteRecord.project_id == project_id,
                TestSuiteRecord.deleted_at.is_(None),
            )
        )
        if suite is None:
            raise HTTPException(status_code=404, detail="Test suite not found")
    if body.protected_question_id:
        question = await session.scalar(
            select(ProtectedQuestionRecord.id).where(
                ProtectedQuestionRecord.id == body.protected_question_id,
                ProtectedQuestionRecord.project_id == project_id,
                ProtectedQuestionRecord.deleted_at.is_(None),
            )
        )
        if question is None:
            raise HTTPException(status_code=404, detail="Protected question not found")
    schedule_id = new_id()
    temporal_schedule_id = (
        f"histograph/schedule/{project.organization_id}/{project_id}/{schedule_id}"
    )
    schedule = ScheduleRecord(
        id=schedule_id,
        organization_id=project.organization_id,
        project_id=project_id,
        suite_id=body.suite_id,
        protected_question_id=body.protected_question_id,
        name=body.name,
        cron_expression=body.cron_expression,
        timezone=body.timezone,
        concurrency_policy=ScheduleConcurrency(body.concurrency_policy),
        active=True,
        temporal_schedule_id=temporal_schedule_id,
        created_by=actor.subject,
    )
    session.add(schedule)
    await session.flush()
    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        await orchestrator.create_schedule(
            schedule_id=schedule.id,
            cron_expression=schedule.cron_expression,
            timezone=schedule.timezone,
            overlap_policy=schedule.concurrency_policy.value,
        )
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project_id,
            action="schedule.created",
            target_type="schedule",
            target_id=schedule.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={
                "name": schedule.name,
                "cron_expression": schedule.cron_expression,
                "timezone": schedule.timezone,
                "concurrency_policy": schedule.concurrency_policy.value,
                "suite_id": schedule.suite_id,
                "protected_question_id": schedule.protected_question_id,
            },
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        await orchestrator.delete_schedule(schedule.id)
        raise HTTPException(status_code=409, detail="Schedule name already exists") from error
    except Exception as error:
        await session.rollback()
        raise HTTPException(status_code=503, detail="Schedule could not be registered") from error
    await session.refresh(schedule)
    return schedule


@router.post(
    "/metadata-events",
    response_model=MetadataEventResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def ingest_metadata_event(
    project_id: str,
    body: MetadataEventRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MetadataEventReceiptRecord:
    project = await authorize_project(session, actor, project_id)
    if actor.type is ActorType.SERVICE and not actor.has_scope("metadata-events:write"):
        raise HTTPException(status_code=403, detail="Insufficient scope")
    existing = await session.scalar(
        select(MetadataEventReceiptRecord).where(
            MetadataEventReceiptRecord.organization_id == project.organization_id,
            MetadataEventReceiptRecord.source == body.source,
            MetadataEventReceiptRecord.idempotency_key == body.idempotency_key,
        )
    )
    if existing:
        return existing
    connection = await session.scalar(
        select(DataHubConnectionRecord).where(
            DataHubConnectionRecord.id == body.datahub_connection_id,
            DataHubConnectionRecord.project_id == project_id,
            DataHubConnectionRecord.deleted_at.is_(None),
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="DataHub connection not found")
    fingerprint = stable_fingerprint(
        {
            "entity_urn": body.entity_urn,
            "event_type": body.event_type,
            "aspect_name": body.aspect_name,
            "aspect_version": body.aspect_version,
            "payload": body.payload,
        }
    )
    receipt = MetadataEventReceiptRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        datahub_connection_id=connection.id,
        source=body.source,
        idempotency_key=body.idempotency_key,
        entity_urn=body.entity_urn,
        event_type=body.event_type,
        aspect_name=body.aspect_name,
        aspect_version=body.aspect_version,
        cursor=body.cursor,
        fingerprint=fingerprint,
        payload_json=body.payload,
        status=ReceiptStatus.RECEIVED,
    )
    session.add(receipt)
    await session.flush()
    run = RunRecord(
        organization_id=project.organization_id,
        project_id=project_id,
        trigger_type=TriggerType.DATAHUB_EVENT,
        trigger_reference=receipt.id,
        idempotency_key=f"metadata-event:{receipt.id}",
        requested_by=actor.subject,
        status=RunStatus.QUEUED,
        configuration_fingerprint=stable_fingerprint(
            {
                "project_id": project_id,
                "datahub_connection_id": connection.id,
                "event_fingerprint": fingerprint,
            }
        ),
        selection_json={"asset_urns": [body.entity_urn]},
        queued_at=datetime.now(UTC),
    )
    session.add(run)
    await session.flush()
    receipt.run_id = run.id
    await session.commit()
    orchestrator: Orchestrator = request.app.state.orchestrator
    try:
        run.workflow_id = await orchestrator.start_run(run.id)
        receipt.status = ReceiptStatus.PROCESSING
        await session.commit()
    except Exception as error:
        run.status = RunStatus.ERROR
        run.error_code = "workflow_start_failed"
        run.error_message = str(error)[:4000]
        run.completed_at = datetime.now(UTC)
        receipt.status = ReceiptStatus.FAILED
        receipt.error_message = "Workflow orchestrator unavailable"
        await session.commit()
        raise HTTPException(status_code=503, detail="Workflow orchestrator unavailable") from error
    await session.refresh(receipt)
    return receipt


def _validate_schedule(body: CreateScheduleRequest) -> None:
    if not croniter.is_valid(body.cron_expression):
        raise HTTPException(status_code=422, detail="Invalid cron expression")
    try:
        ZoneInfo(body.timezone)
    except ZoneInfoNotFoundError as error:
        raise HTTPException(status_code=422, detail="Unknown IANA timezone") from error
