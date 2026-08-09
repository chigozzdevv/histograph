import json
from datetime import datetime

from histograph.models.types import JsonScalar
from histograph.storage.clickhouse import ClickHouseDatabase
from histograph.telemetry.types import Prediction


class TelemetryRepository:
    def __init__(self, database: ClickHouseDatabase):
        self._database = database

    def save(self, prediction: Prediction) -> None:
        self.save_many([prediction])

    def save_many(self, predictions: list[Prediction]) -> None:
        if not predictions:
            return
        self._database.client.insert(
            f"{self._database.name}.predictions",
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
                for prediction in predictions
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

    def feature_values(
        self,
        model: str,
        version: str,
        feature: str,
        start: datetime,
        end: datetime,
    ) -> list[float]:
        result = self._database.client.query(
            f"""
            SELECT argMax(features_json, observed_at)
            FROM {self._database.name}.predictions
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
        result = self._database.client.query(
            f"""
            WITH prediction_window AS (
                SELECT
                    prediction_id,
                    argMax(predicted_class, observed_at) AS latest_predicted_class,
                    max(observed_at) AS prediction_observed_at
                FROM {self._database.name}.predictions
                WHERE model = %(model)s
                  AND version = %(version)s
                  AND observed_at >= %(start)s
                  AND observed_at < %(end)s
                  AND predicted_class IS NOT NULL
                GROUP BY prediction_id
            ), actual_window AS (
                SELECT prediction_id, argMax(actual, observed_at) AS actual
                FROM {self._database.name}.actuals
                WHERE observed_at < %(end)s
                GROUP BY prediction_id
            )
            SELECT p.latest_predicted_class, a.actual
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


def _scalars_equal(left: object, right: JsonScalar) -> bool:
    if isinstance(left, bool) or isinstance(right, bool):
        return isinstance(left, bool) and isinstance(right, bool) and left == right
    if isinstance(left, int | float) and isinstance(right, int | float):
        return float(left) == float(right)
    return type(left) is type(right) and left == right
