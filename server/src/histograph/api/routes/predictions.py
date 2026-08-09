from fastapi import APIRouter, Request, status

from histograph.api.responses import AcceptedEvent
from histograph.telemetry.types import Prediction, PredictionBatch

router = APIRouter(prefix="/v1/events/predictions", tags=["predictions"])


@router.post("", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_prediction(event: Prediction, request: Request) -> AcceptedEvent:
    request.app.state.predictions.ingest(event)
    return AcceptedEvent(event_type="prediction")


@router.post("/batch", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_prediction_batch(batch: PredictionBatch, request: Request) -> AcceptedEvent:
    request.app.state.predictions.ingest_many(batch.events)
    return AcceptedEvent(event_type="prediction", count=len(batch.events))
