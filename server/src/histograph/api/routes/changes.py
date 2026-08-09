from fastapi import APIRouter, Request, status

from histograph.api.responses import AcceptedEvent
from histograph.changes.types import Change

router = APIRouter(prefix="/v1/events/changes", tags=["changes"])


@router.post("", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_change(event: Change, request: Request) -> AcceptedEvent:
    request.app.state.change_ingestion.ingest(event)
    return AcceptedEvent(event_type="change")
