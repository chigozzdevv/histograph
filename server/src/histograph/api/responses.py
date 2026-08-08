from pydantic import BaseModel


class AcceptedEvent(BaseModel):
    accepted: bool = True
    event_type: str
