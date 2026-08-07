import json
from datetime import datetime

import clickhouse_connect

from histograph.contracts.events import Actual, Prediction

SCHEMA = """
CREATE TABLE IF NOT EXISTS {database}.predictions (
    prediction_id String,
    model String,
    version String,
    environment String,
    deployment Nullable(String),
    observed_at DateTime64(3, 'UTC'),
    predicted_class Nullable(String),
    score Nullable(Float64),
    features_json String,
    tags_json String,
    latency_ms Nullable(Float64),
    error_state Nullable(String)
) ENGINE = MergeTree
ORDER BY (model, version, observed_at, prediction_id)
"""

ACTUALS_SCHEMA = """
CREATE TABLE IF NOT EXISTS {database}.actuals (
    prediction_id String,
    actual String,
    observed_at DateTime64(3, 'UTC'),
    metadata_json String
) ENGINE = MergeTree
ORDER BY (prediction_id, observed_at)
"""


class ClickHouseStore:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self._client = clickhouse_connect.get_client(
            host=host,
            port=port,
            username=user,
            password=password,
        )
        self._database = database

    def initialize(self) -> None:
        self._client.command(f"CREATE DATABASE IF NOT EXISTS {self._database}")
        self._client.command(SCHEMA.format(database=self._database))
        self._client.command(ACTUALS_SCHEMA.format(database=self._database))

    def save_prediction(self, prediction: Prediction) -> None:
        self._client.insert(
            f"{self._database}.predictions",
            [
                [
                    prediction.prediction_id,
                    prediction.model,
                    prediction.version,
                    prediction.environment,
                    prediction.deployment,
                    prediction.observed_at,
                    prediction.predicted_class,
                    prediction.score,
                    json.dumps(prediction.features, separators=(",", ":")),
                    json.dumps(prediction.tags, separators=(",", ":")),
                    prediction.latency_ms,
                    prediction.error_state,
                ]
            ],
            column_names=[
                "prediction_id",
                "model",
                "version",
                "environment",
                "deployment",
                "observed_at",
                "predicted_class",
                "score",
                "features_json",
                "tags_json",
                "latency_ms",
                "error_state",
            ],
        )

    def save_actual(self, actual: Actual) -> None:
        self._client.insert(
            f"{self._database}.actuals",
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

    def feature_values(
        self,
        model: str,
        version: str,
        feature: str,
        start: datetime,
        end: datetime,
    ) -> list[float]:
        result = self._client.query(
            f"""
            SELECT JSONExtractFloat(features_json, %(feature)s)
            FROM {self._database}.predictions
            WHERE model = %(model)s
              AND version = %(version)s
              AND observed_at >= %(start)s
              AND observed_at < %(end)s
              AND JSONHas(features_json, %(feature)s)
            ORDER BY observed_at
            """,
            parameters={
                "feature": feature,
                "model": model,
                "version": version,
                "start": start,
                "end": end,
            },
        )
        return [float(row[0]) for row in result.result_rows if row[0] is not None]

    def binary_pairs(
        self,
        model: str,
        version: str,
        start: datetime,
        end: datetime,
    ) -> list[tuple[bool, bool]]:
        result = self._client.query(
            f"""
            SELECT p.predicted_class, a.actual
            FROM {self._database}.predictions AS p
            INNER JOIN {self._database}.actuals AS a
                ON p.prediction_id = a.prediction_id
            WHERE p.model = %(model)s
              AND p.version = %(version)s
              AND p.observed_at >= %(start)s
              AND p.observed_at < %(end)s
            ORDER BY p.observed_at
            """,
            parameters={"model": model, "version": version, "start": start, "end": end},
        )
        pairs: list[tuple[bool, bool]] = []
        for predicted_class, actual_json in result.result_rows:
            predicted = predicted_class == "fraud"
            actual = json.loads(actual_json)
            pairs.append((predicted, bool(actual)))
        return pairs

    def close(self) -> None:
        self._client.close()
