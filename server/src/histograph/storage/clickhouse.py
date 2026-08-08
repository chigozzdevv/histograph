import json
from datetime import datetime

import clickhouse_connect
from clickhouse_connect.driver.client import Client

from histograph.actuals.types import Actual
from histograph.models.types import JsonScalar
from histograph.telemetry.types import Prediction

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
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._client: Client | None = None

    def _connect(self) -> Client:
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
            )
        return self._client

    def initialize(self) -> None:
        client = self._connect()
        client.command(f"CREATE DATABASE IF NOT EXISTS {self._database}")
        client.command(SCHEMA.format(database=self._database))
        client.command(ACTUALS_SCHEMA.format(database=self._database))

    def ping(self) -> None:
        self._connect().command("SELECT 1")

    def save_prediction(self, prediction: Prediction) -> None:
        self._connect().insert(
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
        self._connect().insert(
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
        result = self._connect().query(
            f"""
            SELECT argMax(features_json, observed_at)
            FROM {self._database}.predictions
            WHERE model = %(model)s
              AND version = %(version)s
              AND observed_at >= %(start)s
              AND observed_at < %(end)s
              AND JSONHas(features_json, %(feature)s)
            GROUP BY prediction_id
            """,
            parameters={
                "feature": feature,
                "model": model,
                "version": version,
                "start": start,
                "end": end,
            },
        )
        values: list[float] = []
        for (features_json,) in result.result_rows:
            feature_value = json.loads(features_json).get(feature)
            if isinstance(feature_value, int | float) and not isinstance(feature_value, bool):
                values.append(float(feature_value))
        return values

    def binary_pairs(
        self,
        model: str,
        version: str,
        start: datetime,
        end: datetime,
        positive_class: str,
        positive_actual: JsonScalar,
    ) -> list[tuple[bool, bool]]:
        result = self._connect().query(
            f"""
            WITH prediction_window AS (
                SELECT
                    prediction_id,
                    argMax(predicted_class, observed_at) AS predicted_class,
                    max(observed_at) AS prediction_observed_at
                FROM {self._database}.predictions
                WHERE model = %(model)s
                  AND version = %(version)s
                  AND observed_at >= %(start)s
                  AND observed_at < %(end)s
                  AND predicted_class IS NOT NULL
                GROUP BY prediction_id
            ), actual_window AS (
                SELECT prediction_id, argMax(actual, observed_at) AS actual
                FROM {self._database}.actuals
                WHERE observed_at < %(end)s
                GROUP BY prediction_id
            )
            SELECT p.predicted_class, a.actual
            FROM prediction_window AS p
            INNER JOIN actual_window AS a USING (prediction_id)
            ORDER BY p.prediction_observed_at
            """,
            parameters={"model": model, "version": version, "start": start, "end": end},
        )
        pairs: list[tuple[bool, bool]] = []
        for predicted_class, actual_json in result.result_rows:
            actual = json.loads(actual_json)
            if actual is None:
                continue
            predicted = predicted_class == positive_class
            actual_is_positive = _scalars_equal(actual, positive_actual)
            pairs.append((predicted, actual_is_positive))
        return pairs

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None


def _scalars_equal(left: object, right: JsonScalar) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return float(left) == float(right)
    return type(left) is type(right) and left == right
