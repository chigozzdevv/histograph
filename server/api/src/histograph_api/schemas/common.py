from datetime import datetime

from histograph_domain.base import DomainModel
from pydantic import ConfigDict


class ApiModel(DomainModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AuditFields(ApiModel):
    created_at: datetime
    updated_at: datetime
