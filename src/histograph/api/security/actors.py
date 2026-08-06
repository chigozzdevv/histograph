from enum import StrEnum

from pydantic import Field

from histograph.domain.base import DomainModel


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
