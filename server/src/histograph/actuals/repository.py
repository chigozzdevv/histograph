import json

from histograph.actuals.types import Actual
from histograph.storage.clickhouse import ClickHouseDatabase


class ActualRepository:
    def __init__(self, database: ClickHouseDatabase):
        self._database = database

    def save(self, actual: Actual) -> None:
        self._database.client.insert(
            f"{self._database.name}.actuals",
            [
                [
                    actual.prediction_id,
                    json.dumps(actual.actual, separators=(",", ":")),
                    actual.observed_at,
                    json.dumps(actual.metadata, separators=(",", ":")),
                ]
            ],
            column_names=["prediction_id", "actual", "observed_at", "metadata_json"],
        )
