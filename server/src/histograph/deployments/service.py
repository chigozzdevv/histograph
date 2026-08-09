from typing import Protocol
from uuid import UUID

from histograph.deployments.types import Deployment


class DeploymentWriter(Protocol):
    def save(self, deployment: Deployment) -> UUID: ...


class DeploymentObserver(Protocol):
    def observe_deployment(self, deployment: Deployment) -> None: ...


class DeploymentService:
    def __init__(
        self,
        repository: DeploymentWriter,
        observers: tuple[DeploymentObserver, ...] = (),
    ):
        self._repository = repository
        self._observers = observers

    def ingest(self, deployment: Deployment) -> UUID:
        deployment_id = self._repository.save(deployment)
        for observer in self._observers:
            observer.observe_deployment(deployment)
        return deployment_id
