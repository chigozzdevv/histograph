from typing import Protocol
from uuid import UUID

from histograph.deployments.types import Deployment


class DeploymentWriter(Protocol):
    def save(self, deployment: Deployment) -> UUID: ...


class DeploymentService:
    def __init__(self, repository: DeploymentWriter):
        self._repository = repository

    def ingest(self, deployment: Deployment) -> UUID:
        return self._repository.save(deployment)
