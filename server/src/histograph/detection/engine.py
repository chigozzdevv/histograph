from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID

from histograph.core.time import ensure_utc
from histograph.detection.statistics import (
    BinaryMetrics,
    calculate_binary_metrics,
    population_stability_index,
)
from histograph.monitors.types import Monitor, MonitorEvent
from histograph.storage.clickhouse import ClickHouseStore


@dataclass(frozen=True)
class DetectionResult:
    triggered: bool
    metric: str
    observed_value: float | None
    baseline_value: float | None
    threshold: float
    sample_size: int
    evidence: dict[str, Any]


def _matches(operator: str, observed: float, threshold: float, baseline: float | None) -> bool:
    if operator == "lt":
        return observed < threshold
    if operator == "lte":
        return observed <= threshold
    if operator == "gt":
        return observed > threshold
    if operator == "gte":
        return observed >= threshold
    if operator == "change":
        if baseline is None:
            return False
        return abs(observed - baseline) >= threshold
    raise ValueError(f"Unsupported monitor operator: {operator}")


class DetectionEngine:
    def __init__(self, telemetry: ClickHouseStore):
        self._telemetry = telemetry

    def evaluate_feature_drift(
        self,
        monitor_id: UUID,
        monitor: Monitor,
        feature: str,
        as_of: datetime,
    ) -> tuple[DetectionResult, MonitorEvent | None]:
        end = ensure_utc(as_of)
        current_start = end - timedelta(minutes=monitor.evaluation_window_minutes)
        baseline_start = current_start - timedelta(minutes=monitor.baseline_window_minutes)
        baseline = self._telemetry.feature_values(
            monitor.model,
            monitor.version or "active",
            feature,
            baseline_start,
            current_start,
        )
        current = self._telemetry.feature_values(
            monitor.model,
            monitor.version or "active",
            feature,
            current_start,
            end,
        )
        observed = population_stability_index(baseline, current)
        result = DetectionResult(
            triggered=bool(
                baseline
                and current
                and _matches(monitor.operator, observed, monitor.threshold, 0.0)
            ),
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=0.0,
            threshold=monitor.threshold,
            sample_size=len(current),
            evidence={
                "feature": feature,
                "baseline_window": {
                    "start": baseline_start.isoformat(),
                    "end": current_start.isoformat(),
                    "sample_size": len(baseline),
                },
                "evaluation_window": {
                    "start": current_start.isoformat(),
                    "end": end.isoformat(),
                    "sample_size": len(current),
                },
            },
        )
        event = (
            self._event_from_result(monitor_id, monitor, result, end)
            if result.triggered
            else None
        )
        return result, event

    def evaluate_performance(
        self,
        monitor_id: UUID,
        monitor: Monitor,
        as_of: datetime,
    ) -> tuple[DetectionResult, MonitorEvent | None]:
        end = ensure_utc(as_of)
        current_start = end - timedelta(minutes=monitor.evaluation_window_minutes)
        baseline_start = current_start - timedelta(minutes=monitor.baseline_window_minutes)
        baseline_pairs = self._telemetry.binary_pairs(
            monitor.model,
            monitor.version or "active",
            baseline_start,
            current_start,
        )
        current_pairs = self._telemetry.binary_pairs(
            monitor.model,
            monitor.version or "active",
            current_start,
            end,
        )
        baseline_metrics = calculate_binary_metrics(baseline_pairs)
        current_metrics = calculate_binary_metrics(current_pairs)
        observed = self._metric_value(current_metrics, monitor.metric)
        baseline = self._metric_value(baseline_metrics, monitor.metric)
        triggered = (
            observed is not None
            and bool(current_pairs)
            and _matches(monitor.operator, observed, monitor.threshold, baseline)
        )
        result = DetectionResult(
            triggered=triggered,
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=baseline,
            threshold=monitor.threshold,
            sample_size=len(current_pairs),
            evidence={
                "baseline_window": {
                    "start": baseline_start.isoformat(),
                    "end": current_start.isoformat(),
                    "metrics": self._metrics_dict(baseline_metrics),
                },
                "evaluation_window": {
                    "start": current_start.isoformat(),
                    "end": end.isoformat(),
                    "metrics": self._metrics_dict(current_metrics),
                },
            },
        )
        event = self._event_from_result(monitor_id, monitor, result, end) if triggered else None
        return result, event

    @staticmethod
    def _metric_value(metrics: BinaryMetrics, metric: str) -> float | None:
        value = getattr(metrics, metric, None)
        if value is None and metric not in {
            "precision",
            "recall",
            "false_positive_rate",
            "accuracy",
        }:
            raise ValueError(f"Unsupported binary metric: {metric}")
        return value

    @staticmethod
    def _metrics_dict(metrics: BinaryMetrics) -> dict[str, Any]:
        return {
            "count": metrics.count,
            "positive_predictions": metrics.positive_predictions,
            "true_positives": metrics.true_positives,
            "false_positives": metrics.false_positives,
            "false_negatives": metrics.false_negatives,
            "true_negatives": metrics.true_negatives,
            "precision": metrics.precision,
            "recall": metrics.recall,
            "false_positive_rate": metrics.false_positive_rate,
            "accuracy": metrics.accuracy,
        }

    @staticmethod
    def _event_from_result(
        monitor_id: UUID, monitor: Monitor, result: DetectionResult, occurred_at: datetime
    ) -> MonitorEvent:
        if result.observed_value is None:
            raise ValueError("A triggered detection must have an observed value")
        return MonitorEvent(
            monitor_id=monitor_id,
            model=monitor.model,
            version=monitor.version or "active",
            signal=monitor.signal,
            metric=result.metric,
            observed_value=result.observed_value,
            baseline_value=result.baseline_value,
            threshold=result.threshold,
            occurred_at=occurred_at,
        )
