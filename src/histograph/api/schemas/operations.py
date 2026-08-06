from datetime import datetime

from histograph.api.schemas.common import ApiModel


class TestExecutionResponse(ApiModel):
    id: str
    run_id: str
    protected_question_id: str
    test_version_id: str
    baseline_version_id: str | None
    agent_target_id: str
    status: str
    attempt_count: int
    trace_id: str
    evidence_json: dict | None
    evaluation_json: dict | None
    error_code: str | None
    error_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    updated_at: datetime


class IncidentResponse(ApiModel):
    id: str
    project_id: str
    protected_question_id: str
    fingerprint: str
    status: str
    title: str
    summary: str
    resource_urn: str
    first_run_id: str
    latest_run_id: str
    occurrence_count: int
    consecutive_success_count: int
    datahub_incident_urn: str | None
    resolved_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AuditEventResponse(ApiModel):
    id: str
    project_id: str | None
    actor_type: str
    actor_id: str
    action: str
    target_type: str
    target_id: str
    request_id: str
    source_ip: str | None
    before_fingerprint: str | None
    after_fingerprint: str | None
    details_json: dict
    created_at: datetime
    updated_at: datetime
