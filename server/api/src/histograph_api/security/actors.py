from enum import StrEnum

from histograph_domain.base import DomainModel
from pydantic import Field


class ActorType(StrEnum):
    BOOTSTRAP = "bootstrap"
    USER = "user"
    SERVICE = "service"


class Actor(DomainModel):
    type: ActorType
    subject: str
    organization_id: str | None = None
    project_id: str | None = None
    scopes: frozenset[str] = frozenset()
    claims: dict = Field(default_factory=dict)

    def has_scope(self, scope: str) -> bool:
        return "*" in self.scopes or scope in self.scopes
