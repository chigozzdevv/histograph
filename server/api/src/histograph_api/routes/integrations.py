from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request, status
from histograph_agents import DataHubAnalyticsAgentAdapter
from histograph_datahub import DataHubGraphqlClient, DataHubMcpClient
from histograph_domain import AnalyticsAgentTarget, DataHubConnection
from histograph_security import EnvelopeCipher, stable_fingerprint
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from histograph_api.database.models import AgentTargetRecord, DataHubConnectionRecord
from histograph_api.database.models.common import ConnectionStatus, Role, SecretLocation, new_id
from histograph_api.database.session import get_session
from histograph_api.schemas import (
    AgentTargetResponse,
    CreateAgentTargetRequest,
    CreateDataHubConnectionRequest,
    DataHubConnectionResponse,
    IntegrationTestResponse,
)
from histograph_api.security import Actor, get_actor
from histograph_api.security.authorization import authorize_project
from histograph_api.services.audit import add_audit_event
from histograph_api.services.requests import request_id, source_ip

router = APIRouter(prefix="/projects/{project_id}", tags=["integrations"])


@router.get("/datahub-connections", response_model=tuple[DataHubConnectionResponse, ...])
async def list_datahub_connections(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[DataHubConnectionRecord, ...]:
    await authorize_project(session, actor, project_id)
    records = await session.scalars(
        select(DataHubConnectionRecord)
        .where(
            DataHubConnectionRecord.project_id == project_id,
            DataHubConnectionRecord.deleted_at.is_(None),
        )
        .order_by(DataHubConnectionRecord.version.desc())
    )
    return tuple(records)


@router.post(
    "/datahub-connections",
    response_model=DataHubConnectionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_datahub_connection(
    project_id: str,
    body: CreateDataHubConnectionRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> DataHubConnectionRecord:
    project = await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN})
    connection_id = new_id()
    secret_location = SecretLocation(body.secret_location)
    encrypted_credentials = None
    if body.token:
        cipher: EnvelopeCipher = request.app.state.envelope_cipher
        encrypted_credentials = cipher.encrypt(
            body.token.get_secret_value(),
            context=_secret_context("datahub", project_id, connection_id),
        )
    current_version = await session.scalar(
        select(func.max(DataHubConnectionRecord.version)).where(
            DataHubConnectionRecord.project_id == project_id
        )
    )
    await session.execute(
        update(DataHubConnectionRecord)
        .where(DataHubConnectionRecord.project_id == project_id)
        .values(active=False)
    )
    connection = DataHubConnectionRecord(
        id=connection_id,
        organization_id=project.organization_id,
        project_id=project_id,
        name=body.name,
        mode=body.mode,
        endpoint_url=str(body.endpoint_url),
        mcp_url=str(body.mcp_url),
        deployment_id=body.deployment_id,
        encrypted_credentials=encrypted_credentials,
        secret_location=secret_location,
        status=ConnectionStatus.PENDING,
        capabilities_json={},
        version=(current_version or 0) + 1,
        active=True,
    )
    session.add(connection)
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project_id,
        action="datahub_connection.created",
        target_type="datahub_connection",
        target_id=connection.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        after=_datahub_audit_value(connection),
    )
    await session.commit()
    await session.refresh(connection)
    return connection


@router.post("/datahub-connections/{connection_id}/test", response_model=IntegrationTestResponse)
async def test_datahub_connection(
    project_id: str,
    connection_id: str,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IntegrationTestResponse:
    await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.ENGINEER})
    connection = await _datahub_connection(session, project_id, connection_id)
    if connection.secret_location is SecretLocation.PRIVATE_RUNNER:
        raise HTTPException(
            status_code=409,
            detail="Private-runner credentials must be verified by an enrolled runner",
        )
    if not connection.encrypted_credentials:
        raise HTTPException(status_code=409, detail="DataHub credentials are unavailable")
    connection.status = ConnectionStatus.VERIFYING
    await session.commit()
    try:
        cipher: EnvelopeCipher = request.app.state.envelope_cipher
        token = cipher.decrypt(
            connection.encrypted_credentials,
            context=_secret_context("datahub", project_id, connection.id),
        )
        tools = await DataHubMcpClient(
            DataHubConnection(mcp_url=connection.mcp_url, token=token)
        ).verify()
        graphql = DataHubGraphqlClient(endpoint_url=connection.endpoint_url, token=token)
        try:
            actor_urn = await graphql.verify()
        finally:
            await graphql.close()
        capabilities = {
            "mcp_tools": list(tools),
            "lineage": "get_lineage" in tools,
            "graphql": True,
            "graphql_actor_urn": actor_urn,
            "incident_writeback": "requires_edit_entity_incidents_privilege",
        }
        connection.status = ConnectionStatus.READY
        connection.capabilities_json = capabilities
        connection.last_verified_at = datetime.now(UTC)
        connection.last_error = None
        await session.commit()
    except Exception as error:
        connection.status = ConnectionStatus.FAILED
        connection.last_verified_at = datetime.now(UTC)
        connection.last_error = str(error)[:4000]
        await session.commit()
        raise HTTPException(
            status_code=502, detail="DataHub connection verification failed"
        ) from error
    return IntegrationTestResponse(
        status=connection.status.value,
        capabilities=capabilities,
        verified_at=connection.last_verified_at,
    )


@router.get("/agent-targets", response_model=tuple[AgentTargetResponse, ...])
async def list_agent_targets(
    project_id: str,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> tuple[AgentTargetRecord, ...]:
    await authorize_project(session, actor, project_id)
    records = await session.scalars(
        select(AgentTargetRecord)
        .where(AgentTargetRecord.project_id == project_id, AgentTargetRecord.deleted_at.is_(None))
        .order_by(AgentTargetRecord.name, AgentTargetRecord.version.desc())
    )
    return tuple(records)


@router.post(
    "/agent-targets", response_model=AgentTargetResponse, status_code=status.HTTP_201_CREATED
)
async def create_agent_target(
    project_id: str,
    body: CreateAgentTargetRequest,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> AgentTargetRecord:
    project = await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN})
    target_id = new_id()
    encrypted_credentials = None
    if body.token:
        cipher: EnvelopeCipher = request.app.state.envelope_cipher
        encrypted_credentials = cipher.encrypt(
            body.token.get_secret_value(), context=_secret_context("agent", project_id, target_id)
        )
    current_version = await session.scalar(
        select(func.max(AgentTargetRecord.version)).where(
            AgentTargetRecord.project_id == project_id,
            AgentTargetRecord.name == body.name,
        )
    )
    target = AgentTargetRecord(
        id=target_id,
        organization_id=project.organization_id,
        project_id=project_id,
        name=body.name,
        adapter_type=body.adapter_type,
        base_url=str(body.base_url),
        engine_name=body.engine_name,
        encrypted_credentials=encrypted_credentials,
        secret_location=SecretLocation(body.secret_location),
        status=ConnectionStatus.PENDING,
        capabilities_json={},
        prompt_fingerprint=stable_fingerprint(
            {"adapter": body.adapter_type, "engine_name": body.engine_name}
        ),
        model_identifiers_json=[],
        version=(current_version or 0) + 1,
        active=True,
    )
    session.add(target)
    add_audit_event(
        session,
        actor=actor,
        organization_id=project.organization_id,
        project_id=project_id,
        action="agent_target.created",
        target_type="agent_target",
        target_id=target.id,
        request_id=request_id(request),
        source_ip=source_ip(request),
        after=_agent_audit_value(target),
    )
    await session.commit()
    await session.refresh(target)
    return target


@router.post("/agent-targets/{target_id}/test", response_model=IntegrationTestResponse)
async def test_agent_target(
    project_id: str,
    target_id: str,
    request: Request,
    actor: Annotated[Actor, Depends(get_actor)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> IntegrationTestResponse:
    await authorize_project(session, actor, project_id, {Role.OWNER, Role.ADMIN, Role.AGENT_OWNER})
    target = await _agent_target(session, project_id, target_id)
    token = None
    if target.encrypted_credentials:
        cipher: EnvelopeCipher = request.app.state.envelope_cipher
        token = cipher.decrypt(
            target.encrypted_credentials,
            context=_secret_context("agent", project_id, target.id),
        )
    target.status = ConnectionStatus.VERIFYING
    await session.commit()
    try:
        adapter = DataHubAnalyticsAgentAdapter(
            AnalyticsAgentTarget(
                base_url=target.base_url,
                engine_name=target.engine_name,
                token=token,
            )
        )
        await adapter.health()
        capabilities = {"adapter": target.adapter_type, "streaming": "sse"}
        target.status = ConnectionStatus.READY
        target.capabilities_json = capabilities
        target.last_verified_at = datetime.now(UTC)
        target.last_error = None
        await session.commit()
    except Exception as error:
        target.status = ConnectionStatus.FAILED
        target.last_verified_at = datetime.now(UTC)
        target.last_error = str(error)[:4000]
        await session.commit()
        raise HTTPException(status_code=502, detail="Agent target verification failed") from error
    return IntegrationTestResponse(
        status=target.status.value,
        capabilities=capabilities,
        verified_at=target.last_verified_at,
    )


async def _datahub_connection(
    session: AsyncSession, project_id: str, connection_id: str
) -> DataHubConnectionRecord:
    connection = await session.scalar(
        select(DataHubConnectionRecord).where(
            DataHubConnectionRecord.id == connection_id,
            DataHubConnectionRecord.project_id == project_id,
            DataHubConnectionRecord.deleted_at.is_(None),
        )
    )
    if connection is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return connection


async def _agent_target(
    session: AsyncSession, project_id: str, target_id: str
) -> AgentTargetRecord:
    target = await session.scalar(
        select(AgentTargetRecord).where(
            AgentTargetRecord.id == target_id,
            AgentTargetRecord.project_id == project_id,
            AgentTargetRecord.deleted_at.is_(None),
        )
    )
    if target is None:
        raise HTTPException(status_code=404, detail="Resource not found")
    return target


def _secret_context(kind: str, project_id: str, record_id: str) -> str:
    return f"histograph:{kind}:{project_id}:{record_id}"


def _datahub_audit_value(connection: DataHubConnectionRecord) -> dict:
    return {
        "name": connection.name,
        "mode": connection.mode,
        "mcp_url": connection.mcp_url,
        "secret_location": connection.secret_location.value,
        "version": connection.version,
    }


def _agent_audit_value(target: AgentTargetRecord) -> dict:
    return {
        "name": target.name,
        "adapter_type": target.adapter_type,
        "base_url": target.base_url,
        "engine_name": target.engine_name,
        "secret_location": target.secret_location.value,
        "version": target.version,
    }
