from typing import Any
from urllib.parse import quote, urlsplit
from uuid import UUID

import httpx
from fastapi import APIRouter, HTTPException, Query, Request, status
from pydantic import Field

from histograph.core.events import EventModel

router = APIRouter(prefix="/v1", tags=["product"])


class PlaygroundRequest(EventModel):
    input: dict[str, Any] = Field(min_length=1)


@router.get("/overview")
def overview(request: Request) -> dict[str, Any]:
    return request.app.state.product.overview()


@router.get("/deployments")
def list_deployments(request: Request) -> list[dict[str, Any]]:
    return [
        _deployment_view(item, request.app.state.settings)
        for item in request.app.state.gitops.list_deployments()
    ]


@router.get("/deployments/{deployment_id}")
def get_deployment(deployment_id: UUID, request: Request) -> dict[str, Any]:
    deployment = request.app.state.gitops.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    return _deployment_view(deployment, request.app.state.settings)


@router.post("/deployments/{deployment_id}/predict")
async def predict(
    deployment_id: UUID,
    payload: PlaygroundRequest,
    request: Request,
) -> dict[str, Any]:
    return await _runtime_call(deployment_id, payload.input, request, compare=False)


@router.post("/deployments/{deployment_id}/compare")
async def compare(
    deployment_id: UUID,
    payload: PlaygroundRequest,
    request: Request,
) -> dict[str, Any]:
    result = await _runtime_call(deployment_id, payload.input, request, compare=True)
    return {**result, "telemetry_recorded": False}


@router.get("/activity")
def activity(
    request: Request,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[dict[str, Any]]:
    return request.app.state.product.activity(limit)


@router.get("/integrations")
def integrations(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "github": {
            "configured": request.app.state.github_client is not None,
            "connections": request.app.state.gitops.list_connections(),
        },
        "datahub": {
            "configured": bool(settings.datahub_gms_url),
            "write_back_enabled": settings.datahub_mcp_mutations_enabled,
        },
        "reference_runtime": {
            "control_configured": settings.reference_control_token is not None,
            "allowed_hosts": settings.playground_allowed_hosts,
        },
    }


async def _runtime_call(
    deployment_id: UUID,
    features: dict[str, Any],
    request: Request,
    *,
    compare: bool,
) -> dict[str, Any]:
    _consume_rate_limit(
        request,
        "playground",
        request.app.state.settings.playground_rate_limit_per_minute,
        60,
    )
    deployment = request.app.state.gitops.get_deployment(deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    try:
        if compare:
            return await request.app.state.runtime_connector.compare(deployment, features)
        return await request.app.state.runtime_connector.predict(deployment, features)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except (httpx.HTTPError, RuntimeError) as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"Reference runtime request failed: {error}",
        ) from error


def _deployment_view(deployment: dict[str, Any], settings: Any) -> dict[str, Any]:
    allowed = {
        "id",
        "connection_id",
        "deployment",
        "model",
        "environment",
        "provider",
        "datahub_model_urn",
        "desired_revision",
        "manifest",
        "input_schema",
        "output_schema",
        "examples",
        "observed_state",
        "observed_at",
        "sync_status",
        "repository_owner",
        "repository_name",
        "branch",
        "manifest_path",
        "created_at",
        "updated_at",
    }
    return {
        **{key: value for key, value in deployment.items() if key in allowed},
        "source_links": _source_links(deployment, settings),
    }


def _source_links(deployment: dict[str, Any], settings: Any) -> dict[str, str | None]:
    owner = deployment.get("repository_owner")
    repository = deployment.get("repository_name")
    revision = deployment.get("desired_revision") or deployment.get("branch")
    manifest_path = deployment.get("manifest_path")
    github_base = _github_frontend_url(getattr(settings, "github_api_url", None))

    repository_url = None
    branch_url = None
    manifest_url = None
    if github_base and isinstance(owner, str) and isinstance(repository, str):
        repository_url = f"{github_base}/{quote(owner, safe='')}/{quote(repository, safe='')}"
        branch = deployment.get("branch")
        if isinstance(branch, str):
            branch_url = f"{repository_url}/tree/{quote(branch, safe='')}"
        if isinstance(revision, str) and isinstance(manifest_path, str):
            manifest_url = (
                f"{repository_url}/blob/{quote(revision, safe='')}/"
                f"{quote(manifest_path.lstrip('/'), safe='/')}"
            )

    datahub_url = None
    datahub_base = getattr(settings, "datahub_frontend_url", None)
    model_urn = deployment.get("datahub_model_urn")
    if datahub_base and isinstance(model_urn, str):
        datahub_url = f"{str(datahub_base).rstrip('/')}/mlModels/{quote(model_urn, safe='')}"

    return {
        "repository": repository_url,
        "branch": branch_url,
        "manifest": manifest_url,
        "datahub": datahub_url,
    }


def _github_frontend_url(api_url: str | None) -> str | None:
    if not api_url:
        return None
    parsed = urlsplit(api_url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None
    if parsed.netloc == "api.github.com":
        return "https://github.com"
    return f"{parsed.scheme}://{parsed.netloc}"


def _consume_rate_limit(
    request: Request,
    bucket: str,
    limit: int,
    window_seconds: int,
) -> None:
    client_key = request.client.host if request.client is not None else "unknown"
    if not request.app.state.rate_limits.consume(
        bucket,
        client_key,
        limit=limit,
        window_seconds=window_seconds,
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Request rate limit exceeded",
        )
