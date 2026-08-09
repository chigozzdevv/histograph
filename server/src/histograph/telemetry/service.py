from typing import Protocol

from histograph.telemetry.types import Prediction


class PredictionWriter(Protocol):
    def save(self, prediction: Prediction) -> None: ...

    def save_many(self, predictions: list[Prediction]) -> None: ...


class TelemetryService:
    def __init__(self, repository: PredictionWriter):
        self._repository = repository

    def ingest(self, prediction: Prediction) -> None:
        self._repository.save(prediction)

    def ingest_many(self, predictions: list[Prediction]) -> None:
        self._repository.save_many(predictions)
