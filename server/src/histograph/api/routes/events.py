from fastapi import APIRouter, Request, status
from pydantic import BaseModel

from histograph.contracts.events import Actual, Deployment, Prediction

router = APIRouter(prefix="/v1/events", tags=["events"])


class AcceptedEvent(BaseModel):
    accepted: bool = True
    event_type: str


@router.post("/predictions", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_prediction(event: Prediction, request: Request) -> AcceptedEvent:
    request.app.state.telemetry.save_prediction(event)
    return AcceptedEvent(event_type="prediction")


@router.post("/actuals", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_actual(event: Actual, request: Request) -> AcceptedEvent:
    request.app.state.telemetry.save_actual(event)
    return AcceptedEvent(event_type="actual")


@router.post("/deployments", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_deployment(event: Deployment, request: Request) -> AcceptedEvent:
    request.app.state.control.save_deployment(event)
    return AcceptedEvent(event_type="deployment")
