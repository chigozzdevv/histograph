import json

from histograph.actuals.types import Actual
from histograph.storage.clickhouse import ClickHouseDatabase

SCHEMA = """
CREATE TABLE IF NOT EXISTS {database}.actuals (
    prediction_id String,
    actual String,
    observed_at DateTime64(3, 'UTC'),
    metadata_json String
) ENGINE = MergeTree
ORDER BY (prediction_id, observed_at)
"""


class ActualRepository:
    def __init__(self, database: ClickHouseDatabase):
        self._database = database

    def initialize(self) -> None:
        self._database.client.command(SCHEMA.format(database=self._database.name))

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
