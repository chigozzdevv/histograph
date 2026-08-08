from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import Field

from histograph.agents.investigation.agent import InvestigationAgent
from histograph.core.events import EventModel
from histograph.integrations.datahub.client import DataHubMcpClient, DataHubMcpError

router = APIRouter(prefix="/v1/investigations", tags=["investigations"])


class InvestigationRequest(EventModel):
    max_hops: int = Field(default=3, ge=1, le=3)
    write_back: bool = False


def _registered_model_urn(request: Request, incident: dict[str, object]) -> str:
    model_name = incident.get("model")
    if not isinstance(model_name, str):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident does not identify a registered model",
        )
    model = request.app.state.models.get(model_name)
    if model is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Incident model is not registered",
        )
    model_urn = model.get("datahub_urn")
    if not isinstance(model_urn, str) or not model_urn.strip():
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registered model has no DataHub URN",
        )
    return model_urn


@router.post("/{incident_id}")
async def investigate_incident(
    incident_id: UUID, request_body: InvestigationRequest, request: Request
) -> dict[str, object]:
    incident = request.app.state.incidents.get(incident_id)
    if incident is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    model_urn = _registered_model_urn(request, incident)
    agent = InvestigationAgent(
        request.app.state.incidents,
        DataHubMcpClient(request.app.state.settings),
    )
    try:
        return await agent.investigate(
            incident_id,
            model_urn,
            max_hops=request_body.max_hops,
            write_back=request_body.write_back,
        )
    except DataHubMcpError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
