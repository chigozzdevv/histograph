from datetime import datetime

from pydantic import Field, field_validator

from histograph.api.schemas.common import ApiModel


class ConnectGitHubInstallationRequest(ApiModel):
    installation_id: int = Field(gt=0)


class GitHubInstallationResponse(ApiModel):
    id: str
    organization_id: str
    installation_id: int
    account_login: str
    account_type: str
    repository_selection: str
    permissions_json: dict
    suspended_at: datetime | None
    created_at: datetime
    updated_at: datetime


class AssetMapping(ApiModel):
    pattern: str = Field(min_length=1, max_length=512)
    asset_urns: tuple[str, ...] = Field(min_length=1, max_length=500)

    @field_validator("asset_urns")
    @classmethod
    def validate_asset_urns(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
        if not normalized or any(not item.startswith("urn:li:") for item in normalized):
            raise ValueError("asset_urns must contain valid DataHub URNs")
        return normalized


class ConnectRepositoryRequest(ApiModel):
    github_installation_id: str
    repository_id: int = Field(gt=0)
    asset_mappings: tuple[AssetMapping, ...] = ()
    run_all_when_unmapped: bool = True
    protected_branches: tuple[str, ...] = ()
    run_draft_pull_requests: bool = False

    @field_validator("protected_branches")
    @classmethod
    def validate_protected_branches(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        normalized = tuple(dict.fromkeys(item.strip() for item in value if item.strip()))
        if any(len(item) > 255 for item in normalized):
            raise ValueError("protected branch names cannot exceed 255 characters")
        return normalized


class RepositoryConnectionResponse(ApiModel):
    id: str
    organization_id: str
    project_id: str
    github_installation_id: str
    repository_id: int
    owner: str
    name: str
    full_name: str
    default_branch: str
    configuration_json: dict
    active: bool
    created_at: datetime
    updated_at: datetime
