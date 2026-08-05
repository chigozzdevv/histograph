from datetime import datetime

from histograph_domain import AssetAssertions, ResponseAssertions, ResultAssertions, SqlAssertions
from pydantic import Field

from histograph_api.schemas.common import ApiModel


class CreateTestSuiteRequest(ApiModel):
    name: str = Field(min_length=1, max_length=160)
    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{1,78}[a-z0-9]$")
    description: str | None = Field(default=None, max_length=4000)


class TestSuiteResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class CreateProtectedQuestionRequest(ApiModel):
    stable_key: str = Field(pattern=r"^[a-z0-9][a-z0-9-]*$", max_length=160)
    name: str = Field(min_length=1, max_length=160)
    description: str | None = Field(default=None, max_length=4000)
    criticality: str = Field(default="medium", pattern=r"^(low|medium|high|critical)$")
    owner_reference: str | None = Field(default=None, max_length=255)
    agent_target_id: str
    question: str = Field(min_length=1, max_length=10_000)
    context_query: str | None = Field(default=None, max_length=1000)
    time_anchor: dict = Field(default_factory=lambda: {"mode": "relative"})
    assets: AssetAssertions = Field(default_factory=AssetAssertions)
    sql: SqlAssertions = Field(default_factory=SqlAssertions)
    result: ResultAssertions = Field(default_factory=ResultAssertions)
    response: ResponseAssertions = Field(default_factory=ResponseAssertions)
    stability: dict = Field(default_factory=dict)
    limits: dict = Field(default_factory=lambda: {"timeout_seconds": 180})
    tags: tuple[str, ...] = ()


class ProtectedQuestionResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    suite_id: str
    stable_key: str
    name: str
    description: str | None
    criticality: str
    owner_reference: str | None
    active_version_id: str | None
    active_baseline_id: str | None
    active: bool
    created_at: datetime
    updated_at: datetime


class TestVersionResponse(ApiModel):
    id: str
    protected_question_id: str
    agent_target_id: str
    version: int
    configuration_json: dict
    fingerprint: str
    created_by: str
    created_at: datetime


class BaselineDependencyInput(ApiModel):
    asset_urn: str = Field(min_length=1, max_length=1024)
    field_path: str = Field(default="", max_length=512)
    dependency_type: str = Field(min_length=1, max_length=80)
    evidence: dict = Field(default_factory=dict)


class CreateBaselineRequest(ApiModel):
    test_version_id: str
    source_execution_id: str | None = None
    evidence: dict
    assertions: dict
    environment_fingerprint: str = Field(min_length=64, max_length=64)
    dependencies: tuple[BaselineDependencyInput, ...] = ()


class ApproveBaselineRequest(ApiModel):
    justification: str = Field(min_length=8, max_length=4000)


class BaselineResponse(ApiModel):
    id: str
    protected_question_id: str
    test_version_id: str
    source_execution_id: str | None
    version: int
    status: str
    evidence_json: dict
    assertions_json: dict
    environment_fingerprint: str
    approved_by: str | None
    approved_at: datetime | None
    approval_justification: str | None
    created_at: datetime
