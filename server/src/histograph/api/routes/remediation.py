from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Header, HTTPException, Request, status

from histograph.remediation.auth import StaticTokenAuthorizer, authorize_callback
from histograph.remediation.service import RemediationService
from histograph.remediation.types import ApprovalDecision, ExecutionCallback, ExecutionResult

router = APIRouter(prefix="/v1", tags=["remediation"])


@router.get("/incidents/{incident_id}/actions")
def list_incident_actions(incident_id: UUID, request: Request) -> list[dict[str, object]]:
    if request.app.state.incidents.get(incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return request.app.state.remediation.list_for_incident(incident_id)


@router.get("/actions/{action_id}")
def get_action(action_id: UUID, request: Request) -> dict[str, object]:
    action = request.app.state.remediation.get(action_id)
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Remediation action not found"
        )
    gitops = getattr(request.app.state, "gitops", None)
    pull_request = gitops.pull_request_for_action(action_id) if gitops is not None else None
    return {
        **action,
        "approval": request.app.state.remediation.approval(action_id),
        "timeline": request.app.state.remediation.events(action_id),
        "pull_request": pull_request,
    }


@router.post("/actions/{action_id}/approval")
def decide_action(
    action_id: UUID,
    decision: ApprovalDecision,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    try:
        principal = StaticTokenAuthorizer(request.app.state.settings.approval_tokens).authorize(
            authorization
        )
        action = RemediationService(request.app.state.remediation).decide(
            action_id, principal.actor_id, decision
        )
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error
    if action is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Remediation action not found"
        )
    return action


@router.post("/actions/{action_id}/result")
def record_execution_result(
    action_id: UUID,
    callback: ExecutionCallback,
    request: Request,
    authorization: Annotated[str | None, Header()] = None,
) -> dict[str, object]:
    try:
        authorize_callback(authorization, request.app.state.settings.remediation_callback_token)
    except PermissionError as error:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(error)) from error
    current = request.app.state.remediation.get(action_id)
    if current is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Remediation action not found"
        )
    if current["status"] != "executing":
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Only an executing remediation action can accept a result callback",
        )
    external_id = current.get("external_execution_id")
    if external_id is not None and external_id != callback.external_execution_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Execution callback identifier does not match the tracked execution",
        )
    updated = request.app.state.remediation.complete_execution(
        action_id, ExecutionResult.model_validate(callback.model_dump())
    )
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Remediation action execution state changed before the callback was applied",
        )
    return updated
