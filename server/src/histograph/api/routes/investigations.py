from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from histograph.agents.investigation.agent import InvestigationAgent
from histograph.integrations.datahub.client import DataHubMcpClient, DataHubMcpError

router = APIRouter(prefix="/v1/investigations", tags=["investigations"])


class InvestigationRequest(BaseModel):
    model_urn: str = Field(min_length=1, max_length=500)
    max_hops: int = Field(default=3, ge=1, le=3)
    write_back: bool = False


@router.post("/{incident_id}")
async def investigate_incident(
    incident_id: UUID, request_body: InvestigationRequest, request: Request
) -> dict[str, object]:
    if request.app.state.control.get_incident(incident_id) is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Incident not found")
    agent = InvestigationAgent(
        request.app.state.control,
        DataHubMcpClient(request.app.state.settings),
    )
    try:
        return await agent.investigate(
            incident_id,
            request_body.model_urn,
            max_hops=request_body.max_hops,
            write_back=request_body.write_back,
        )
    except DataHubMcpError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(error),
        ) from error
