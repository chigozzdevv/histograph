from collections.abc import Collection

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from histograph.api.database.models import MembershipRecord, ProjectRecord, UserRecord
from histograph.api.database.models.common import Role
from histograph.api.security.actors import Actor, ActorType


async def authorize_organization(
    session: AsyncSession,
    actor: Actor,
    organization_id: str,
    roles: Collection[Role] | None = None,
) -> None:
    if actor.type is ActorType.BOOTSTRAP:
        return
    if actor.type is ActorType.SERVICE:
        if actor.organization_id != organization_id:
            _not_found()
        if actor.project_id is not None:
            _not_found()
        if roles is not None and not actor.has_scope("control-plane:write"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient scope",
            )
        return
    membership = await session.scalar(
        select(MembershipRecord)
        .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
        .where(
            MembershipRecord.organization_id == organization_id,
            UserRecord.external_subject == actor.subject,
            UserRecord.deleted_at.is_(None),
        )
    )
    if membership is None:
        _not_found()
    if roles is not None and membership.role not in roles:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Insufficient role")


async def authorize_project(
    session: AsyncSession,
    actor: Actor,
    project_id: str,
    roles: Collection[Role] | None = None,
) -> ProjectRecord:
    project = await session.scalar(
        select(ProjectRecord).where(
            ProjectRecord.id == project_id, ProjectRecord.deleted_at.is_(None)
        )
    )
    if project is None:
        _not_found()
    if actor.type is ActorType.SERVICE:
        if actor.organization_id != project.organization_id:
            _not_found()
        if actor.project_id and actor.project_id != project_id:
            _not_found()
        if roles is not None and not actor.has_scope("control-plane:write"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient scope",
            )
        return project
    await authorize_organization(session, actor, project.organization_id, roles)
    return project


def _not_found() -> None:
    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Resource not found")
