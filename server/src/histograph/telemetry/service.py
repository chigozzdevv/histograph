from typing import Protocol

from histograph.telemetry.types import Prediction


class PredictionWriter(Protocol):
    def save(self, prediction: Prediction) -> None: ...


class TelemetryService:
    def __init__(self, repository: PredictionWriter):
        self._repository = repository

    def ingest(self, prediction: Prediction) -> None:
        self._repository.save(prediction)
