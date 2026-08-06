from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from histograph.api.schemas.common import ApiModel


class RunSelection(ApiModel):
    suite_ids: tuple[str, ...] = ()
    test_ids: tuple[str, ...] = ()
    asset_urns: tuple[str, ...] = ()
    all_active: bool = False

    @model_validator(mode="after")
    def validate_selection(self) -> "RunSelection":
        if not (self.suite_ids or self.test_ids or self.asset_urns or self.all_active):
            raise ValueError("Select suites, tests, changed assets, or all active tests")
        return self


class CreateRunRequest(ApiModel):
    trigger_type: Literal["manual", "api"] = "manual"
    trigger_reference: str | None = Field(default=None, max_length=1024)
    selection: RunSelection


class RunResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    trigger_type: str
    trigger_reference: str | None
    idempotency_key: str
    requested_by: str
    status: str
    workflow_id: str | None
    configuration_fingerprint: str
    selection_json: dict
    impact_plan_json: dict | None
    report_json: dict | None
    error_code: str | None
    error_message: str | None
    queued_at: datetime
    planned_at: datetime | None
    started_at: datetime | None
    completed_at: datetime | None
    cancellation_requested_at: datetime | None
    superseded_by_run_id: str | None
    created_at: datetime
    updated_at: datetime


class RunListResponse(ApiModel):
    items: tuple[RunResponse, ...]


class RunEventResponse(ApiModel):
    id: str
    test_execution_id: str
    event_id: str
    sequence: int
    event_type: str
    trace_id: str
    event_timestamp: datetime
    payload_json: dict
