from typing import Protocol

from histograph.actuals.types import Actual


class ActualWriter(Protocol):
    def save(self, actual: Actual) -> None: ...

    def save_many(self, actuals: list[Actual]) -> None: ...


class ActualService:
    def __init__(self, repository: ActualWriter):
        self._repository = repository

    def ingest(self, actual: Actual) -> None:
        self._repository.save(actual)

    def ingest_many(self, actuals: list[Actual]) -> None:
        self._repository.save_many(actuals)
