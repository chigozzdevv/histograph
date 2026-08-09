from collections.abc import Callable
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, HTTPException, Request, status
from pydantic import BaseModel, Field

from histograph.core.time import utc_now
from histograph.detection.service import (
    EvaluationOutcome,
    MonitorEvaluationService,
    MonitorSignalMismatch,
)

router = APIRouter(prefix="/v1/detection", tags=["detection"])


class FeatureDriftCheck(BaseModel):
    feature: str | None = Field(default=None, min_length=1, max_length=200)
    as_of: datetime | None = None


class PerformanceCheck(BaseModel):
    as_of: datetime | None = None
    reference_version: str | None = Field(default=None, min_length=1, max_length=100)


def _service(request: Request) -> MonitorEvaluationService:
    return MonitorEvaluationService(
        request.app.state.monitors,
        request.app.state.deployments,
        request.app.state.models,
        request.app.state.telemetry,
        request.app.state.incidents,
    )


def _evaluate(call: Callable[[], EvaluationOutcome]) -> EvaluationOutcome:
    try:
        return call()
    except LookupError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except MonitorSignalMismatch as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error
    except ValueError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error


@router.post("/monitors/{monitor_id}/feature-drift")
def check_feature_drift(
    monitor_id: UUID,
    request_body: FeatureDriftCheck,
    request: Request,
) -> dict[str, object]:
    outcome = _evaluate(
        lambda: _service(request).evaluate(
            monitor_id,
            request_body.as_of or utc_now(),
            feature=request_body.feature,
            expected_signal="feature_drift",
        )
    )
    return outcome.as_dict()


@router.post("/monitors/{monitor_id}/performance")
def check_performance(
    monitor_id: UUID,
    request_body: PerformanceCheck,
    request: Request,
) -> dict[str, object]:
    outcome = _evaluate(
        lambda: _service(request).evaluate(
            monitor_id,
            request_body.as_of or utc_now(),
            reference_version=request_body.reference_version,
            expected_signal="performance",
        )
    )
    return outcome.as_dict()
