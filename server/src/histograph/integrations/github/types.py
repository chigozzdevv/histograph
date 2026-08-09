from datetime import datetime
from typing import Any, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from histograph.core.events import EventModel
from histograph.models.types import JsonScalar


class AliasModel(EventModel):
    model_config = ConfigDict(
        extra="forbid",
        str_strip_whitespace=True,
        populate_by_name=True,
    )


class GitHubConnectionCreate(EventModel):
    installation_id: int = Field(gt=0)
    repository_owner: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    repository_name: str = Field(pattern=r"^[A-Za-z0-9_.-]+$", max_length=100)
    branch: str = Field(default="main", min_length=1, max_length=200)
    manifest_path: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_manifest_path(self) -> "GitHubConnectionCreate":
        path = self.manifest_path
        if path.startswith("/") or ".." in path.split("/"):
            raise ValueError("Manifest path must be repository-relative and cannot contain '..'")
        if not path.endswith((".yaml", ".yml")):
            raise ValueError("Deployment manifest must use a .yaml or .yml extension")
        return self


class ManifestMetadata(AliasModel):
    name: str = Field(min_length=1, max_length=200)


class ManifestModel(AliasModel):
    name: str = Field(min_length=1, max_length=200)
    task: Literal["binary_classification"]
    positive_class: str = Field(alias="positiveClass", min_length=1, max_length=200)
    positive_actual: JsonScalar = Field(alias="positiveActual")
    datahub_urn: str = Field(alias="datahubModelUrn", min_length=1, max_length=500)


class RuntimeTarget(AliasModel):
    provider: str = Field(min_length=1, max_length=100)
    endpoint: str | None = Field(default=None, max_length=500)


class RepositoryResource(AliasModel):
    path: str = Field(min_length=1, max_length=500)

    @model_validator(mode="after")
    def validate_path(self) -> "RepositoryResource":
        if self.path.startswith("/"):
            raise ValueError("Repository resource paths must be relative")
        if any(part in {"", "."} for part in self.path.split("/")):
            raise ValueError("Repository resource paths must be normalized")
        return self


class ModelInterface(AliasModel):
    input_schema: RepositoryResource = Field(alias="inputSchema")
    output_schema: RepositoryResource = Field(alias="outputSchema")
    examples: RepositoryResource


class ModelRelease(AliasModel):
    version: str = Field(min_length=1, max_length=100)
    artifact: str = Field(min_length=1, max_length=1000)
    configuration: dict[str, JsonScalar] = Field(default_factory=dict)
    traffic_percentage: float = Field(alias="trafficPercentage", ge=0, le=100)
    rollback_version: str | None = Field(
        default=None, alias="rollbackVersion", min_length=1, max_length=100
    )
    rollback_artifact: str | None = Field(
        default=None, alias="rollbackArtifact", min_length=1, max_length=1000
    )

    @model_validator(mode="after")
    def require_complete_rollback_target(self) -> "ModelRelease":
        if (self.rollback_version is None) != (self.rollback_artifact is None):
            raise ValueError("Model rollback version and artifact must be configured together")
        return self


class FeatureRelease(AliasModel):
    name: str = Field(min_length=1, max_length=300)
    asset_urn: str = Field(alias="assetUrn", min_length=1, max_length=1000)
    input_feature: str | None = Field(
        default=None, alias="inputFeature", min_length=1, max_length=300
    )
    version: str = Field(min_length=1, max_length=200)
    configuration: dict[str, JsonScalar] = Field(default_factory=dict)
    rollback_version: str | None = Field(
        default=None, alias="rollbackVersion", min_length=1, max_length=200
    )
    rollback_configuration: dict[str, JsonScalar] | None = Field(
        default=None, alias="rollbackConfiguration"
    )

    @model_validator(mode="after")
    def require_rollback_version_for_configuration(self) -> "FeatureRelease":
        if self.rollback_configuration is not None and self.rollback_version is None:
            raise ValueError("Feature rollback configuration requires a rollback version")
        if "scaleMultiplier" in self.configuration and self.input_feature is None:
            raise ValueError("Feature scaleMultiplier requires an explicit inputFeature")
        return self


class DeploymentSpec(AliasModel):
    environment: str = Field(default="production", min_length=1, max_length=100)
    model: ManifestModel
    runtime: RuntimeTarget
    interface: ModelInterface | None = None
    stable: ModelRelease
    candidate: ModelRelease | None = None
    features: list[FeatureRelease] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_traffic(self) -> "DeploymentSpec":
        candidate_traffic = self.candidate.traffic_percentage if self.candidate else 0.0
        if abs(self.stable.traffic_percentage + candidate_traffic - 100.0) > 1e-6:
            raise ValueError("Stable and candidate traffic percentages must total 100")
        if self.stable.traffic_percentage <= 0:
            raise ValueError("Stable model traffic must be greater than zero")
        if self.candidate is not None and self.candidate.version == self.stable.version:
            raise ValueError("Stable and candidate versions must differ")
        feature_urns = [feature.asset_urn for feature in self.features]
        if len(feature_urns) != len(set(feature_urns)):
            raise ValueError("Feature release asset URNs must be unique")
        return self


class ModelDeploymentManifest(AliasModel):
    api_version: Literal["histograph.ai/v1"] = Field(alias="apiVersion")
    kind: Literal["ModelDeployment"]
    metadata: ManifestMetadata
    spec: DeploymentSpec


class GitHubRepositoryFile(EventModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=False)

    content: str
    blob_sha: str = Field(min_length=1)
    revision: str = Field(min_length=1)


class ResolvedModelInterface(EventModel):
    input_schema: dict[str, Any]
    output_schema: dict[str, Any]
    examples: list[dict[str, Any]]


class CreatedPullRequest(EventModel):
    number: int = Field(gt=0)
    url: str = Field(min_length=1)
    head_branch: str = Field(min_length=1)


class CreatedDeployment(EventModel):
    id: int = Field(gt=0)
    revision: str = Field(min_length=1)


class GitOpsDeploymentView(EventModel):
    id: UUID
    connection_id: UUID
    deployment: str
    model: str
    environment: str
    provider: str
    datahub_model_urn: str
    desired_revision: str
    manifest: dict[str, Any]
    observed_state: dict[str, Any] | None
    observed_at: datetime | None
    sync_status: Literal["desired_only", "in_sync", "out_of_sync"]
