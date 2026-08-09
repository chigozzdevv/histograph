import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from histograph.integrations.github.auth import (
    authorize_configuration,
    verify_webhook_signature,
)
from histograph.integrations.github.types import GitHubConnectionCreate

router = APIRouter(prefix="/v1/integrations/github", tags=["github"])


def _authorize(request: Request, authorization: str | None) -> None:
    try:
        authorize_configuration(
            authorization, request.app.state.settings.github_configuration_token
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error


@router.post("/connections", status_code=status.HTTP_201_CREATED)
def create_connection(
    connection: GitHubConnectionCreate,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _authorize(request, authorization)
    connection_id = request.app.state.github_integration.create_connection(connection)
    return {"id": connection_id, "connection": connection.model_dump(mode="json")}


@router.get("/connections")
def list_connections(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, object]]:
    _authorize(request, authorization)
    return request.app.state.gitops.list_connections()


@router.post("/connections/{connection_id}/sync")
async def sync_connection(
    connection_id: UUID,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    _authorize(request, authorization)
    try:
        return await request.app.state.github_integration.sync(connection_id)
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error


@router.get("/deployments")
def list_deployments(
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> list[dict[str, object]]:
    _authorize(request, authorization)
    return request.app.state.gitops.list_deployments()


@router.post("/webhook", status_code=status.HTTP_202_ACCEPTED)
async def github_webhook(request: Request) -> dict[str, object]:
    body = await request.body()
    try:
        verify_webhook_signature(
            body,
            request.headers.get("X-Hub-Signature-256"),
            request.app.state.settings.github_webhook_secret,
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    delivery_id = request.headers.get("X-GitHub-Delivery")
    event_type = request.headers.get("X-GitHub-Event")
    if not delivery_id or not event_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub delivery and event headers are required",
        )
    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="GitHub webhook body is not valid JSON"
        ) from error
    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="GitHub webhook body must be a JSON object",
        )
    if not request.app.state.gitops.begin_delivery(delivery_id, event_type):
        return {"status": "duplicate", "delivery_id": delivery_id}
    try:
        result = await request.app.state.github_webhooks.handle(event_type, payload)
        request.app.state.gitops.complete_delivery(delivery_id)
        return {"delivery_id": delivery_id, **result}
    except Exception as error:
        request.app.state.gitops.fail_delivery(delivery_id, str(error))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="GitHub webhook processing failed",
        ) from error
