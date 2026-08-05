from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from histograph_security import TokenManager
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from histograph_api.database.models import (
    MembershipRecord,
    OrganizationRecord,
    ProjectRecord,
    ServiceIdentityRecord,
    UserRecord,
)
from histograph_api.database.models.common import Role
from histograph_api.database.session import get_session
from histograph_api.schemas import (
    CreateOrganizationRequest,
    IssuedServiceIdentityResponse,
    IssueServiceIdentityRequest,
    OrganizationResponse,
)
from histograph_api.security import Actor, get_actor
from histograph_api.security.actors import ActorType
from histograph_api.security.authorization import authorize_organization
from histograph_api.services.audit import add_audit_event
from histograph_api.services.requests import request_id, source_ip

router = APIRouter(prefix="/organizations", tags=["organizations"])


@router.get("", response_model=tuple[OrganizationResponse, ...])
async def list_organizations(
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[OrganizationRecord, ...]:
    query = select(OrganizationRecord).where(OrganizationRecord.deleted_at.is_(None))
    if actor.type is ActorType.SERVICE:
        query = query.where(OrganizationRecord.id == actor.organization_id)
    elif actor.type is ActorType.USER:
        query = (
            query.join(
                MembershipRecord,
                MembershipRecord.organization_id == OrganizationRecord.id,
            )
            .join(UserRecord, UserRecord.id == MembershipRecord.user_id)
            .where(UserRecord.external_subject == actor.subject)
        )
    records = await session.scalars(query.order_by(OrganizationRecord.name))
    return tuple(records)


@router.post("", response_model=OrganizationResponse, status_code=status.HTTP_201_CREATED)
async def create_organization(
    body: CreateOrganizationRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrganizationRecord:
    if actor.type is ActorType.SERVICE:
        raise HTTPException(
            status_code=403, detail="Service identities cannot create organizations"
        )
    organization = OrganizationRecord(name=body.name, slug=body.slug)
    user = await session.scalar(
        select(UserRecord).where(UserRecord.external_subject == actor.subject)
    )
    if user is None:
        user = UserRecord(
            external_subject=actor.subject,
            email=body.owner_email,
            display_name=body.owner_display_name,
        )
        session.add(user)
    session.add(organization)
    try:
        await session.flush()
        session.add(
            MembershipRecord(
                organization_id=organization.id,
                user_id=user.id,
                role=Role.OWNER,
            )
        )
        add_audit_event(
            session,
            actor=actor,
            organization_id=organization.id,
            action="organization.created",
            target_type="organization",
            target_id=organization.id,
            request_id=request_id(request),
            source_ip=source_ip(request),
            after={"name": organization.name, "slug": organization.slug},
        )
        await session.commit()
    except IntegrityError as error:
        await session.rollback()
        raise HTTPException(status_code=409, detail="Organization slug already exists") from error
    await session.refresh(organization)
    return organization


@router.get("/{organization_id}", response_model=OrganizationResponse)
async def get_organization(
    organization_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> OrganizationRecord:
    await authorize_organization(session, actor, organization_id)
    organization = await session.scalar(
        select(OrganizationRecord).where(
            OrganizationRecord.id == organization_id,
            OrganizationRecord.deleted_at.is_(None),
        )
    )
    if organization is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return organization


@router.post(
    "/{organization_id}/service-identities",
    response_model=IssuedServiceIdentityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def issue_service_identity(
    organization_id: str,
    body: IssueServiceIdentityRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IssuedServiceIdentityResponse:
    await authorize_organization(session, actor, organization_id, {Role.OWNER, Role.ADMIN})
    if body.project_id:
        project = await session.scalar(
            select(ProjectRecord).where(
                ProjectRecord.id == body.project_id,
                ProjectRecord.organization_id == organization_id,
                ProjectRecord.deleted_at.is_(None),
            )
        )
        if project is None:
            raise HTTPException(status_code=404, detail="Resource not found")
    token: TokenManager = request.app.state.token_manager
    issued = token.issue()
    identity = ServiceIdentityRecord(
        organization_id=organization_id,
        project_id=body.project_id,
        name=body.name,
        token_prefix=issued.prefix,
        token_digest=issued.digest,
        scopes_json=list(dict.fromkeys(body.scopes)),
        expires_at=body.expires_at,
    )
    session.add(identity)
    await session.flush()
    add_audit_event(
        session,
        actor=actor,
        organization_id=organization_id,
        project_id=body.project_id,
        action="service_identity.issued",
        target_type="service_identity",
        target_id=identity.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        after={"name": identity.name, "scopes": identity.scopes_json},
    )
    await session.commit()
    return IssuedServiceIdentityResponse(
        id=identity.id,
        name=identity.name,
        project_id=identity.project_id,
        token=issued.plaintext,
        token_prefix=issued.prefix,
        scopes=tuple(identity.scopes_json),
        expires_at=identity.expires_at,
    )
