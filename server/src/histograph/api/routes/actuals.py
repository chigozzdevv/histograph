from fastapi import APIRouter, Request, status

from histograph.actuals.types import Actual
from histograph.api.responses import AcceptedEvent

router = APIRouter(prefix="/v1/events/actuals", tags=["actuals"])


@router.post("", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_actual(event: Actual, request: Request) -> AcceptedEvent:
    request.app.state.actuals.ingest(event)
    return AcceptedEvent(event_type="actual")
