from datetime import datetime

from pydantic import ConfigDict

from histograph.domain.base import DomainModel


class ApiModel(DomainModel):
    model_config = ConfigDict(extra="forbid", from_attributes=True)


class AuditFields(ApiModel):
    created_at: datetime
    updated_at: datetime
