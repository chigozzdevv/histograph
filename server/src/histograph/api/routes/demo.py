import hmac
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Query, Request, status
from pydantic import Field

from histograph.core.events import EventModel

router = APIRouter(prefix="/v1/demo/scenarios", tags=["demo"])


class StartScenarioRequest(EventModel):
    deployment_id: UUID
    scenario: str = Field(default="model_canary_regression", pattern="^model_canary_regression$")


@router.post("", status_code=status.HTTP_202_ACCEPTED)
def start_scenario(
    payload: StartScenarioRequest,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    actor = _authorize_control(request, authorization)
    if actor == "public-demo":
        client_key = request.client.host if request.client is not None else "unknown"
        if not request.app.state.rate_limits.consume(
            "demo-scenario",
            client_key,
            limit=request.app.state.settings.demo_rate_limit_per_hour,
            window_seconds=3600,
        ):
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Demo scenario rate limit exceeded",
            )
    deployment = request.app.state.gitops.get_deployment(payload.deployment_id)
    if deployment is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deployment not found")
    manifest = deployment.get("manifest")
    spec = manifest.get("spec") if isinstance(manifest, dict) else None
    candidate = spec.get("candidate") if isinstance(spec, dict) else None
    if not isinstance(candidate, dict) or float(candidate.get("trafficPercentage", 0)) <= 0:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Reset the deployment to an active candidate before starting a scenario",
        )
    try:
        run_id = request.app.state.demo_runs.start(deployment, actor)
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    return _public_view(request.app.state.demo_runs.get(run_id))


@router.get("")
def list_scenarios(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
) -> list[dict[str, Any]]:
    return [_public_view(item) for item in request.app.state.demo_runs.list_all(limit)]


@router.get("/{run_id}")
def get_scenario(run_id: UUID, request: Request) -> dict[str, Any]:
    run = request.app.state.demo_runs.refresh(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo scenario not found")
    return _public_view(run)


@router.post("/{run_id}/reset", status_code=status.HTTP_202_ACCEPTED)
async def reset_scenario(
    run_id: UUID,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, Any]:
    _authorize_control(request, authorization)
    run = request.app.state.demo_runs.get(run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Demo scenario not found")
    if run["status"] not in {"resolved", "failed"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only a terminal demo scenario can be reset",
        )
    result = run.get("result")
    if not isinstance(result, dict) or not isinstance(result.get("baseline_manifest"), str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Demo scenario has no saved baseline manifest",
        )
    existing = result.get("reset")
    if isinstance(existing, dict):
        return existing
    try:
        pull_request = await request.app.state.github_integration.create_demo_reset(
            run["deployment_id"], run_id, result["baseline_manifest"]
        )
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
    reset = {
        "status": "pull_request_open",
        "pull_request_number": pull_request.number,
        "pull_request_url": pull_request.url,
        "head_branch": pull_request.head_branch,
    }
    request.app.state.demo_runs.record_reset(run_id, reset)
    return reset


def _authorize_control(request: Request, authorization: str | None) -> str:
    settings = request.app.state.settings
    if settings.demo_public_scenarios_enabled and authorization is None:
        return "public-demo"
    expected = settings.demo_control_token
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Demo scenario control is not configured",
        )
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not hmac.compare_digest(token, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid demo control token",
        )
    return "demo-controller"


def _public_view(run: dict[str, Any] | None) -> dict[str, Any]:
    if run is None:
        raise RuntimeError("Demo scenario was not persisted")
    result = run.get("result")
    public_result = dict(result) if isinstance(result, dict) else {}
    public_result.pop("baseline_manifest", None)
    allowed = {
        "id",
        "deployment_id",
        "status",
        "stage",
        "monitor_id",
        "incident_id",
        "action_id",
        "created_at",
        "updated_at",
        "finished_at",
        "last_error",
    }
    return {
        **{key: value for key, value in run.items() if key in allowed},
        "result": public_result,
    }
