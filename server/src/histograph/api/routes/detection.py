from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from histograph.core.time import utc_now
from histograph.detection.engine import DetectionEngine
from histograph.incidents.service import IncidentService
from histograph.models.types import ModelDefinition
from histograph.monitors.types import Monitor

router = APIRouter(prefix="/v1/detection", tags=["detection"])


class FeatureDriftCheck(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    as_of: datetime | None = None


class PerformanceCheck(BaseModel):
    as_of: datetime | None = None
    reference_version: str | None = Field(default=None, min_length=1, max_length=100)


def _monitor(request: Request, monitor_id: UUID) -> Monitor:
    record = request.app.state.monitors.get(monitor_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    monitor = Monitor(
        model=record["model"],
        version=record["version"],
        environment=record["environment"],
        deployment=record["deployment"],
        signal=record["signal"],
        metric=record["metric"],
        operator=record["operator"],
        threshold=record["threshold"],
        baseline_window_minutes=record["baseline_window_minutes"],
        evaluation_window_minutes=record["evaluation_window_minutes"],
        minimum_sample_size=record["minimum_sample_size"],
        enabled=record["enabled"],
    )
    if not monitor.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Monitor is disabled",
        )
    if monitor.version is not None:
        return monitor

    active_versions = request.app.state.deployments.active_versions(
        monitor.model,
        environment=monitor.environment,
        deployment=monitor.deployment,
    )
    versions = sorted({record["version"] for record in active_versions})
    if not versions:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="No active deployment version found; set an explicit monitor version",
        )
    if len(versions) > 1:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Multiple active versions found; set an explicit monitor version",
        )
    return monitor.model_copy(update={"version": versions[0]})


def _model(request: Request, name: str) -> ModelDefinition:
    record = request.app.state.models.get(name)
    if record is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Registered model definition not found",
        )
    return ModelDefinition(
        name=record["name"],
        task=record["task"],
        positive_class=record["positive_class"],
        positive_actual=record["positive_actual"],
        datahub_urn=record["datahub_urn"],
    )


@router.post("/monitors/{monitor_id}/feature-drift")
def check_feature_drift(
    monitor_id: UUID,
    request_body: FeatureDriftCheck,
    request: Request,
) -> dict[str, object]:
    monitor = _monitor(request, monitor_id)
    if monitor.signal != "feature_drift":
        raise HTTPException(status_code=422, detail="Monitor is not configured for feature drift")
    result, event = DetectionEngine(request.app.state.telemetry).evaluate_feature_drift(
        monitor_id, monitor, request_body.feature, request_body.as_of or utc_now()
    )
    incident_id = None
    if event is not None:
        event_id = request.app.state.monitors.record_event(event, result.evidence)
        event = event.model_copy(update={"id": event_id})
        incident_id = IncidentService(request.app.state.incidents).create_from_monitor_event(
            event, result.evidence
        )
    return {
        "status": result.status,
        "triggered": result.triggered,
        "incident_id": incident_id,
        "metric": result.metric,
        "observed_value": result.observed_value,
        "baseline_value": result.baseline_value,
        "threshold": result.threshold,
        "sample_size": result.sample_size,
        "comparison": result.comparison,
        "evidence": result.evidence,
    }


@router.post("/monitors/{monitor_id}/performance")
def check_performance(
    monitor_id: UUID,
    request_body: PerformanceCheck,
    request: Request,
) -> dict[str, object]:
    monitor = _monitor(request, monitor_id)
    if monitor.signal != "performance":
        raise HTTPException(status_code=422, detail="Monitor is not configured for performance")
    engine = DetectionEngine(request.app.state.telemetry)
    if request_body.reference_version is None:
        result, event = engine.evaluate_performance(
            monitor_id,
            monitor,
            _model(request, monitor.model),
            request_body.as_of or utc_now(),
        )
    else:
        try:
            result, event = engine.evaluate_performance_against_version(
                monitor_id,
                monitor,
                _model(request, monitor.model),
                request_body.reference_version,
                request_body.as_of or utc_now(),
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    incident_id = None
    if event is not None:
        event_id = request.app.state.monitors.record_event(event, result.evidence)
        event = event.model_copy(update={"id": event_id})
        incident_id = IncidentService(request.app.state.incidents).create_from_monitor_event(
            event, result.evidence
        )
    return {
        "status": result.status,
        "triggered": result.triggered,
        "incident_id": incident_id,
        "metric": result.metric,
        "observed_value": result.observed_value,
        "baseline_value": result.baseline_value,
        "threshold": result.threshold,
        "sample_size": result.sample_size,
        "comparison": result.comparison,
        "evidence": result.evidence,
    }
