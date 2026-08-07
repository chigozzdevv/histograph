from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from histograph.contracts.events import Monitor
from histograph.core.time import utc_now
from histograph.detection.engine import DetectionEngine
from histograph.incidents.service import IncidentService

router = APIRouter(prefix="/v1/detection", tags=["detection"])


class FeatureDriftCheck(BaseModel):
    feature: str = Field(min_length=1, max_length=200)
    as_of: datetime | None = None


class PerformanceCheck(BaseModel):
    as_of: datetime | None = None


def _monitor(request: Request, monitor_id: UUID) -> Monitor:
    record = request.app.state.control.get_monitor(monitor_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Monitor not found")
    return Monitor(
        model=record["model"],
        version=record["version"],
        signal=record["signal"],
        metric=record["metric"],
        operator=record["operator"],
        threshold=record["threshold"],
        baseline_window_minutes=record["baseline_window_minutes"],
        evaluation_window_minutes=record["evaluation_window_minutes"],
        enabled=record["enabled"],
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
        incident_id = IncidentService(request.app.state.control).create_from_monitor_event(
            event, result.evidence
        )
    return {
        "triggered": result.triggered,
        "incident_id": incident_id,
        "metric": result.metric,
        "observed_value": result.observed_value,
        "baseline_value": result.baseline_value,
        "threshold": result.threshold,
        "sample_size": result.sample_size,
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
    result, event = DetectionEngine(request.app.state.telemetry).evaluate_performance(
        monitor_id, monitor, request_body.as_of or utc_now()
    )
    incident_id = None
    if event is not None:
        incident_id = IncidentService(request.app.state.control).create_from_monitor_event(
            event, result.evidence
        )
    return {
        "triggered": result.triggered,
        "incident_id": incident_id,
        "metric": result.metric,
        "observed_value": result.observed_value,
        "baseline_value": result.baseline_value,
        "threshold": result.threshold,
        "sample_size": result.sample_size,
        "evidence": result.evidence,
    }
