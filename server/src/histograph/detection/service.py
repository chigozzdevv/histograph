from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal, Protocol
from uuid import UUID

from histograph.detection.engine import DetectionEngine, DetectionResult, DetectionTelemetry
from histograph.incidents.service import IncidentService, IncidentStore
from histograph.models.types import ModelDefinition
from histograph.monitors.types import Monitor, MonitorEvent


class MonitorStore(Protocol):
    def get(self, monitor_id: UUID) -> dict[str, Any] | None: ...

    def record_event(self, event: MonitorEvent, evidence: dict[str, Any]) -> UUID: ...


class DeploymentStore(Protocol):
    def active_versions(
        self,
        model: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> list[dict[str, Any]]: ...


class ModelStore(Protocol):
    def get(self, name: str) -> dict[str, Any] | None: ...


class MonitorSignalMismatch(ValueError):
    """Raised when an endpoint requests the wrong evaluator for a stored monitor."""


@dataclass(frozen=True)
class EvaluationOutcome:
    monitor: Monitor
    result: DetectionResult
    incident_id: UUID | None

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.result.status,
            "triggered": self.result.triggered,
            "incident_id": self.incident_id,
            "metric": self.result.metric,
            "observed_value": self.result.observed_value,
            "baseline_value": self.result.baseline_value,
            "threshold": self.result.threshold,
            "sample_size": self.result.sample_size,
            "comparison": self.result.comparison,
            "evidence": self.result.evidence,
        }


class MonitorEvaluationService:
    def __init__(
        self,
        monitors: MonitorStore,
        deployments: DeploymentStore,
        models: ModelStore,
        telemetry: DetectionTelemetry,
        incidents: IncidentStore,
    ):
        self._monitors = monitors
        self._deployments = deployments
        self._models = models
        self._engine = DetectionEngine(telemetry)
        self._incidents = incidents

    def evaluate(
        self,
        monitor_id: UUID,
        as_of: datetime,
        *,
        feature: str | None = None,
        reference_version: str | None = None,
        expected_signal: Literal["performance", "feature_drift"] | None = None,
        persist: bool = True,
    ) -> EvaluationOutcome:
        record = self._monitors.get(monitor_id)
        if record is None:
            raise LookupError("Monitor not found")
        configured_feature = _configured_value("feature", record.get("feature"), feature)
        configured_reference = _configured_value(
            "reference version", record.get("reference_version"), reference_version
        )
        monitor = _monitor_from_record(
            record,
            feature=configured_feature,
            reference_version=configured_reference,
        )
        if not monitor.enabled:
            raise ValueError("Monitor is disabled")
        if expected_signal is not None and monitor.signal != expected_signal:
            raise MonitorSignalMismatch(
                f"Monitor is not configured for {expected_signal.replace('_', ' ')}"
            )
        monitor = self._resolve_version(monitor)

        if monitor.signal == "feature_drift":
            if configured_feature is None:
                raise ValueError("Feature drift monitor has no configured feature")
            result, event = self._engine.evaluate_feature_drift(
                monitor_id, monitor, configured_feature, as_of
            )
        else:
            model = self._model(monitor.model)
            if configured_reference is None:
                result, event = self._engine.evaluate_performance(monitor_id, monitor, model, as_of)
            else:
                result, event = self._engine.evaluate_performance_against_version(
                    monitor_id, monitor, model, configured_reference, as_of
                )

        incident_id = None
        if persist and event is not None:
            event_id = self._monitors.record_event(event, result.evidence)
            persisted_event = event.model_copy(update={"id": event_id})
            incident_id = IncidentService(self._incidents).create_from_monitor_event(
                persisted_event, result.evidence
            )
        return EvaluationOutcome(monitor=monitor, result=result, incident_id=incident_id)

    def _resolve_version(self, monitor: Monitor) -> Monitor:
        if monitor.version is not None:
            return monitor
        active = self._deployments.active_versions(
            monitor.model,
            environment=monitor.environment,
            deployment=monitor.deployment,
        )
        versions = sorted(
            {record["version"] for record in active if isinstance(record.get("version"), str)}
        )
        if not versions:
            raise ValueError("No active deployment version found; set an explicit monitor version")
        if len(versions) > 1:
            raise ValueError("Multiple active versions found; set an explicit monitor version")
        return monitor.model_copy(update={"version": versions[0]})

    def _model(self, name: str) -> ModelDefinition:
        record = self._models.get(name)
        if record is None:
            raise ValueError("Registered model definition not found")
        return ModelDefinition(
            name=record["name"],
            task=record["task"],
            positive_class=record["positive_class"],
            positive_actual=record["positive_actual"],
            datahub_urn=record["datahub_urn"],
        )


def _monitor_from_record(
    record: dict[str, Any],
    *,
    feature: str | None = None,
    reference_version: str | None = None,
) -> Monitor:
    return Monitor(
        model=record["model"],
        version=record.get("version"),
        environment=record.get("environment", "production"),
        deployment=record.get("deployment"),
        signal=record["signal"],
        metric=record["metric"],
        feature=feature,
        reference_version=reference_version,
        operator=record["operator"],
        threshold=record["threshold"],
        baseline_window_minutes=record["baseline_window_minutes"],
        evaluation_window_minutes=record["evaluation_window_minutes"],
        minimum_sample_size=record["minimum_sample_size"],
        check_interval_seconds=record.get("check_interval_seconds", 60),
        enabled=record["enabled"],
    )


def _configured_value(label: str, stored: str | None, supplied: str | None) -> str | None:
    if supplied is not None and stored is not None and supplied != stored:
        raise ValueError(f"Requested {label} does not match the stored monitor definition")
    return stored or supplied
