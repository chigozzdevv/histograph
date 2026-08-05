from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph_api.database.models import ProjectRecord
from histograph_api.database.models.common import ProjectEnvironment, Role
from histograph_api.database.session import get_session
from histograph_api.schemas import CreateProjectRequest, ProjectResponse, UpdateProjectRequest
from histograph_api.security import Actor, get_actor
from histograph_api.security.authorization import authorize_organization, authorize_project
from histograph_api.services.audit import add_audit_event
from histograph_api.services.requests import request_id, source_ip

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=tuple[ProjectResponse, ...])
async def list_projects(
    organization_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[ProjectRecord, ...]:
    await authorize_organization(session, actor, organization_id)
    projects = await session.scalars(
        select(ProjectRecord)
        .where(
            ProjectRecord.organization_id == organization_id,
            ProjectRecord.deleted_at.is_(None),
        )
        .order_by(ProjectRecord.name)
    )
    return tuple(projects)


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
async def create_project(
    body: CreateProjectRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectRecord:
    await authorize_organization(session, actor, body.organization_id, {Role.OWNER, Role.ADMIN})
    project = ProjectRecord(
        organization_id=body.organization_id,
        name=body.name,
        slug=body.slug,
        environment=ProjectEnvironment(body.environment),
        timezone=body.timezone,
        retention_days=body.retention_days,
        max_concurrent_runs=body.max_concurrent_runs,
    )
    session.add(project)
    try:
        await session.flush()
        add_audit_event(
            session,
            actor=actor,
            organization_id=project.organization_id,
            project_id=project.id,
            action="project.created",
            target_type="project",
            target_id=project.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after=_audit_value(project),
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Project slug already exists") from error
    await session.refresh(project)
    return project


@router.get("/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectRecord:
    return await authorize_project(session, actor, project_id)


@router.patch("/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    body: UpdateProjectRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> ProjectRecord:
    project = await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN})
    before = _audit_value(project)
    changes = body.model_dump(exclude_unset=True)
    if "default_trigger_policy" in changes:
        changes["default_trigger_policy_json"] = changes.pop("default_trigger_policy")
    for field, value in changes.items():
        setattr(project, field, value)
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project.id,
        action="project.updated",
        target_type="project",
        target_id=project.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        before=before,
        after=_audit_value(project),
    )
    await session.commit()
    await session.refresh(project)
    return project


def _audit_value(project: ProjectRecord) -> dict:
    return {
        "name": project.name,
        "slug": project.slug,
        "environment": project.environment.value,
        "timezone": project.timezone,
        "retention_days": project.retention_days,
        "max_concurrent_runs": project.max_concurrent_runs,
        "default_trigger_policy": project.default_trigger_policy_json,
    }
