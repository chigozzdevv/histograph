from fastapi import APIRouter, Request, status

from histograph.api.responses import AcceptedEvent
from histograph.deployments.types import Deployment

router = APIRouter(prefix="/v1/events/deployments", tags=["deployments"])


@router.post("", response_model=AcceptedEvent, status_code=status.HTTP_202_ACCEPTED)
def ingest_deployment(event: Deployment, request: Request) -> AcceptedEvent:
    request.app.state.deployment_ingestion.ingest(event)
    return AcceptedEvent(event_type="deployment")
