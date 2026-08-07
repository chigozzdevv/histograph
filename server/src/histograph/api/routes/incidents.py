from uuid import UUID

from fastapi import APIRouter, HTTPException, Query, Request, status

router = APIRouter(prefix="/v1/incidents", tags=["incidents"])


@router.get("")
def list_incidents(
    request: Request,
    limit: int = Query(default=50, ge=1, le=200),
) -> list[dict[str, object]]:
    return request.app.state.control.list_incidents(limit)


@router.get("/{incident_id}")
def get_incident(incident_id: UUID, request: Request) -> dict[str, object]:
    incident = request.app.state.control.get_incident(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    return incident
