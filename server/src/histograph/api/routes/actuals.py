from fastapi import APIRouter, Request, status

from histograph.actuals.types import Actual, ActualBatch
from histograph.api.responses import AcceptedEvent

router = APIRouter(prefix="/v1/events/actuals", tags=["actuals"])


@router.post("", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_actual(event: Actual, request: Request) -> AcceptedEvent:
    request.app.state.actuals.ingest(event)
    return AcceptedEvent(event_type="actual")


@router.post("/batch", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_actual_batch(batch: ActualBatch, request: Request) -> AcceptedEvent:
    request.app.state.actuals.ingest_many(batch.events)
    return AcceptedEvent(event_type="actual", count=len(batch.events))
