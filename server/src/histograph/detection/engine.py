from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from histograph.core.time import ensure_utc
from histograph.detection.statistics import (
    BinaryMetrics,
    calculate_binary_metrics,
    population_stability_index,
)
from histograph.models.types import ModelDefinition
from histograph.monitors.types import Monitor, MonitorEvent


class DetectionTelemetry(Protocol):
    def feature_values(
        self,
        model: str,
        version: str,
        feature: str,
        start: datetime,
        end: datetime,
    ) -> list[float]: ...

    def binary_pairs(
        self,
        model: str,
        version: str,
        start: datetime,
        end: datetime,
        positive_class: str,
        positive_actual: bool | int | float | str,
    ) -> list[tuple[bool, bool]]: ...


@dataclass(frozen=True)
class DetectionResult:
    status: Literal["evaluated", "insufficient_data"]
    triggered: bool
    metric: str
    observed_value: float | None
    baseline_value: float | None
    threshold: float
    sample_size: int
    comparison: dict[str, float | str | None]
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
    if operator == "decrease":
        if baseline is None:
            return False
        return baseline - observed >= threshold
    if operator == "increase":
        if baseline is None:
            return False
        return observed - baseline >= threshold
    raise ValueError(f"Unsupported monitor operator: {operator}")


_LOWER_IS_BETTER = {"false_positive_rate", "false_negative_rate", "psi"}


def _comparison(metric: str, baseline: float | None, observed: float | None) -> dict[str, Any]:
    if baseline is None or observed is None:
        return {
            "absolute_change": None,
            "absolute_change_percentage_points": None,
            "relative_change_percent": None,
            "degradation_percent": None,
            "direction": "unavailable",
        }

    absolute_change = observed - baseline
    relative_change = None
    if baseline != 0:
        relative_change = absolute_change / abs(baseline) * 100

    lower_is_better = metric in _LOWER_IS_BETTER
    degraded = absolute_change > 0 if lower_is_better else absolute_change < 0
    improved = absolute_change < 0 if lower_is_better else absolute_change > 0
    degradation_percent = None
    if relative_change is not None:
        degradation_percent = relative_change if lower_is_better else -relative_change

    return {
        "absolute_change": absolute_change,
        "absolute_change_percentage_points": absolute_change * 100,
        "relative_change_percent": relative_change,
        "degradation_percent": degradation_percent if degraded else 0.0,
        "direction": "degraded" if degraded else "improved" if improved else "unchanged",
    }


class DetectionEngine:
    def __init__(self, telemetry: DetectionTelemetry):
        self._telemetry = telemetry

    def evaluate_feature_drift(
        self,
        monitor_id: UUID,
        monitor: Monitor,
        feature: str,
        as_of: datetime,
    ) -> tuple[DetectionResult, MonitorEvent | None]:
        if not monitor.enabled:
            raise ValueError("Disabled monitors cannot be evaluated")
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
        sufficient_data = (
            len(baseline) >= monitor.minimum_sample_size
            and len(current) >= monitor.minimum_sample_size
        )
        observed = population_stability_index(baseline, current) if sufficient_data else None
        result = DetectionResult(
            status="evaluated" if sufficient_data else "insufficient_data",
            triggered=(
                sufficient_data
                and observed is not None
                and _matches(monitor.operator, observed, monitor.threshold, 0.0)
            ),
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=0.0 if sufficient_data else None,
            threshold=monitor.threshold,
            sample_size=len(current),
            comparison=_comparison(monitor.metric, 0.0 if sufficient_data else None, observed),
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
            self._event_from_result(monitor_id, monitor, result, end) if result.triggered else None
        )
        return result, event

    def evaluate_performance(
        self,
        monitor_id: UUID,
        monitor: Monitor,
        model: ModelDefinition,
        as_of: datetime,
    ) -> tuple[DetectionResult, MonitorEvent | None]:
        if not monitor.enabled:
            raise ValueError("Disabled monitors cannot be evaluated")
        if model.name != monitor.model:
            raise ValueError("Monitor model does not match the registered model definition")
        end = ensure_utc(as_of)
        current_start = end - timedelta(minutes=monitor.evaluation_window_minutes)
        baseline_start = current_start - timedelta(minutes=monitor.baseline_window_minutes)
        baseline_pairs = self._telemetry.binary_pairs(
            monitor.model,
            monitor.version or "active",
            baseline_start,
            current_start,
            model.positive_class,
            model.positive_actual,
        )
        current_pairs = self._telemetry.binary_pairs(
            monitor.model,
            monitor.version or "active",
            current_start,
            end,
            model.positive_class,
            model.positive_actual,
        )
        baseline_metrics = calculate_binary_metrics(baseline_pairs)
        current_metrics = calculate_binary_metrics(current_pairs)
        observed = self._metric_value(current_metrics, monitor.metric)
        baseline = self._metric_value(baseline_metrics, monitor.metric)
        sufficient_data = (
            len(baseline_pairs) >= monitor.minimum_sample_size
            and len(current_pairs) >= monitor.minimum_sample_size
        )
        triggered = (
            sufficient_data
            and observed is not None
            and _matches(monitor.operator, observed, monitor.threshold, baseline)
        )
        result = DetectionResult(
            status="evaluated" if sufficient_data else "insufficient_data",
            triggered=triggered,
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=baseline,
            threshold=monitor.threshold,
            sample_size=len(current_pairs),
            comparison=_comparison(monitor.metric, baseline, observed),
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

    def evaluate_performance_against_version(
        self,
        monitor_id: UUID,
        monitor: Monitor,
        model: ModelDefinition,
        reference_version: str,
        as_of: datetime,
    ) -> tuple[DetectionResult, MonitorEvent | None]:
        if not monitor.enabled:
            raise ValueError("Disabled monitors cannot be evaluated")
        if monitor.version is None:
            raise ValueError("Canary comparisons require an explicit candidate version")
        if monitor.version == reference_version:
            raise ValueError("Candidate and reference versions must differ")
        if model.name != monitor.model:
            raise ValueError("Monitor model does not match the registered model definition")

        end = ensure_utc(as_of)
        current_start = end - timedelta(minutes=monitor.evaluation_window_minutes)
        reference_pairs = self._telemetry.binary_pairs(
            monitor.model,
            reference_version,
            current_start,
            end,
            model.positive_class,
            model.positive_actual,
        )
        candidate_pairs = self._telemetry.binary_pairs(
            monitor.model,
            monitor.version,
            current_start,
            end,
            model.positive_class,
            model.positive_actual,
        )
        reference_metrics = calculate_binary_metrics(reference_pairs)
        candidate_metrics = calculate_binary_metrics(candidate_pairs)
        baseline = self._metric_value(reference_metrics, monitor.metric)
        observed = self._metric_value(candidate_metrics, monitor.metric)
        sufficient_data = (
            len(reference_pairs) >= monitor.minimum_sample_size
            and len(candidate_pairs) >= monitor.minimum_sample_size
        )
        triggered = (
            sufficient_data
            and observed is not None
            and _matches(monitor.operator, observed, monitor.threshold, baseline)
        )
        comparison = _comparison(monitor.metric, baseline, observed)
        result = DetectionResult(
            status="evaluated" if sufficient_data else "insufficient_data",
            triggered=triggered,
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=baseline,
            threshold=monitor.threshold,
            sample_size=len(candidate_pairs),
            comparison=comparison,
            evidence={
                "comparison_type": "candidate_against_reference_version",
                "window": {"start": current_start.isoformat(), "end": end.isoformat()},
                "reference": {
                    "version": reference_version,
                    "metrics": self._metrics_dict(reference_metrics),
                },
                "candidate": {
                    "version": monitor.version,
                    "metrics": self._metrics_dict(candidate_metrics),
                },
                "comparison": comparison,
            },
        )
        event = (
            self._event_from_result(monitor_id, monitor, result, end) if result.triggered else None
        )
        return result, event

    def evaluate_recovery_performance(
        self,
        monitor: Monitor,
        model: ModelDefinition,
        recovery_version: str,
        baseline_value: float,
        not_before: datetime,
        as_of: datetime,
    ) -> DetectionResult:
        """Evaluate only labeled traffic observed after remediation was applied."""
        if not monitor.enabled:
            raise ValueError("Disabled monitors cannot be evaluated")
        if monitor.signal != "performance":
            raise ValueError("Recovery performance requires a performance monitor")
        if model.name != monitor.model:
            raise ValueError("Monitor model does not match the registered model definition")
        start = ensure_utc(not_before)
        end = ensure_utc(as_of)
        if end <= start:
            raise ValueError("Recovery evaluation must end after remediation was applied")

        pairs = self._telemetry.binary_pairs(
            monitor.model,
            recovery_version,
            start,
            end,
            model.positive_class,
            model.positive_actual,
        )
        metrics = calculate_binary_metrics(pairs)
        observed = self._metric_value(metrics, monitor.metric)
        sufficient_data = len(pairs) >= monitor.minimum_sample_size and observed is not None
        triggered = (
            sufficient_data
            and observed is not None
            and _matches(monitor.operator, observed, monitor.threshold, baseline_value)
        )
        comparison = _comparison(monitor.metric, baseline_value, observed)
        return DetectionResult(
            status="evaluated" if sufficient_data else "insufficient_data",
            triggered=triggered,
            metric=monitor.metric,
            observed_value=observed,
            baseline_value=baseline_value,
            threshold=monitor.threshold,
            sample_size=len(pairs),
            comparison=comparison,
            evidence={
                "comparison_type": "post_remediation_version_against_incident_baseline",
                "window": {"start": start.isoformat(), "end": end.isoformat()},
                "recovery": {
                    "version": recovery_version,
                    "metrics": self._metrics_dict(metrics),
                },
                "incident_baseline": {
                    "metric": monitor.metric,
                    "value": baseline_value,
                },
                "comparison": comparison,
            },
        )

    @staticmethod
    def _metric_value(metrics: BinaryMetrics, metric: str) -> float | None:
        value = getattr(metrics, metric, None)
        if value is None and metric not in {
            "precision",
            "recall",
            "f1",
            "false_positive_rate",
            "false_negative_rate",
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
            "f1": metrics.f1,
            "false_positive_rate": metrics.false_positive_rate,
            "false_negative_rate": metrics.false_negative_rate,
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
            affected_slice={
                key: value
                for key, value in {
                    "environment": monitor.environment,
                    "deployment": monitor.deployment,
                }.items()
                if value is not None
            },
        )
