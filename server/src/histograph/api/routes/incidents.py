from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

from histograph.incidents.service import IncidentService
from histograph.incidents.types import IncidentTransition

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.get("")
def list_incidents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    return request.app.state.incidents.list(limit)


@router.get("/{incident_id}")
def get_incident(incident_id: UUID, request: Request) -> dict[str, object]:
    incident = request.app.state.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return {**incident, "timeline": request.app.state.incidents.events(incident_id)}


@router.patch("/{incident_id}")
def transition_incident(
    incident_id: UUID,
    transition: IncidentTransition,
    request: Request,
) -> dict[str, object]:
    try:
        incident = IncidentService(request.app.state.incidents).transition(
            incident_id, transition
        )
    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
