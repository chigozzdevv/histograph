from typing import Annotated, Literal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import (
    AuditEventRecord,
    IncidentRecord,
    RunRecord,
    TestExecutionRecord,
)
from histograph.api.database.models.common import IncidentStatus
from histograph.api.database.session import get_session
from histograph.api.schemas import AuditEventResponse, IncidentResponse, TestExecutionResponse
from histograph.api.security import Actor, get_actor
from histograph.api.security.authorization import authorize_project

router = APIRouter(prefix="/projects/{project_id}", tags=["operations"])


@router.get("/incidents", response_model=tuple[IncidentResponse, ...])
async def list_incidents(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    incident_status: Literal["open", "resolved"] | None = None,
    limit: int = 100,
) -> tuple[IncidentRecord, ...]:
    await authorize_project(session, actor, project_id)
    statement = select(IncidentRecord).where(IncidentRecord.project_id == project_id)
    if incident_status:
        statement = statement.where(IncidentRecord.status == IncidentStatus(incident_status))
    records = await session.scalars(
        statement.order_by(IncidentRecord.updated_at.desc()).limit(min(max(limit, 1), 500))
    )
    return tuple(records)


@router.get("/audit-events", response_model=tuple[AuditEventResponse, ...])
async def list_audit_events(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 100,
) -> tuple[AuditEventRecord, ...]:
    project = await authorize_project(session, actor, project_id)
    records = await session.scalars(
        select(AuditEventRecord)
        .where(
            AuditEventRecord.organization_id == project.organization_id,
            AuditEventRecord.project_id == project_id,
        )
        .order_by(AuditEventRecord.created_at.desc())
        .limit(min(max(limit, 1), 500))
    )
    return tuple(records)


@router.get(
    "/runs/{run_id}/executions",
    response_model=tuple[TestExecutionResponse, ...],
)
async def list_run_executions(
    project_id: str,
    run_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[TestExecutionRecord, ...]:
    await authorize_project(session, actor, project_id)
    run = await session.scalar(
        select(RunRecord.id).where(RunRecord.id == run_id, RunRecord.project_id == project_id)
    )
    if run is None:
        raise HTTPException(status_code=404, detail="Run not found")
    records = await session.scalars(
        select(TestExecutionRecord)
        .where(TestExecutionRecord.run_id == run_id)
        .order_by(TestExecutionRecord.created_at)
    )
    return tuple(records)
