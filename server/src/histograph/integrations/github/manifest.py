from copy import deepcopy
from typing import Any

import yaml

from histograph.integrations.github.types import ModelDeploymentManifest


class UnsafeRollback(ValueError):
    """Raised when a manifest does not declare enough information for a bounded rollback."""


def parse_manifest(content: str) -> ModelDeploymentManifest:
    try:
        payload = yaml.safe_load(content)
    except yaml.YAMLError as error:
        raise ValueError(f"Deployment manifest is not valid YAML: {error}") from error
    if not isinstance(payload, dict):
        raise ValueError("Deployment manifest must contain one YAML object")
    return ModelDeploymentManifest.model_validate(payload)


def render_rollback(content: str, action: dict[str, Any]) -> str:
    manifest = parse_manifest(content)
    payload = manifest.model_dump(mode="json", by_alias=True, exclude_none=True)
    updated = deepcopy(payload)
    action_type = action.get("action_type")
    target = action.get("target")
    if not isinstance(target, dict):
        raise UnsafeRollback("Remediation action has no structured target")
    _require_target_match(manifest, target)

    if action_type == "stop_canary":
        _stop_canary(updated, manifest, target)
    elif action_type == "rollback_model":
        _rollback_model(updated, manifest, target)
    elif action_type == "rollback_release":
        _rollback_feature(updated, manifest, target)
    else:
        raise UnsafeRollback(f"Unsupported GitOps remediation action: {action_type}")

    validated = ModelDeploymentManifest.model_validate(updated)
    return yaml.safe_dump(
        validated.model_dump(mode="json", by_alias=True, exclude_none=True),
        sort_keys=False,
        allow_unicode=True,
    )


def _require_target_match(manifest: ModelDeploymentManifest, target: dict[str, Any]) -> None:
    expected = (
        manifest.metadata.name,
        manifest.spec.model.name,
        manifest.spec.environment,
    )
    actual = (
        target.get("deployment"),
        target.get("model"),
        target.get("environment", "production"),
    )
    if actual != expected:
        raise UnsafeRollback("Remediation target does not match the imported deployment manifest")


def _stop_canary(
    payload: dict[str, Any],
    manifest: ModelDeploymentManifest,
    target: dict[str, Any],
) -> None:
    candidate = manifest.spec.candidate
    if candidate is None or candidate.version != target.get("version"):
        raise UnsafeRollback("Candidate version does not match the remediation target")
    payload["spec"]["stable"]["trafficPercentage"] = 100.0
    payload["spec"]["candidate"]["trafficPercentage"] = 0.0


def _rollback_model(
    payload: dict[str, Any],
    manifest: ModelDeploymentManifest,
    target: dict[str, Any],
) -> None:
    stable = manifest.spec.stable
    if stable.version != target.get("version"):
        raise UnsafeRollback("Active model version does not match the remediation target")
    if stable.rollback_version is None or stable.rollback_artifact is None:
        raise UnsafeRollback("Manifest does not declare an explicit model rollback target")
    payload["spec"]["stable"] = {
        "version": stable.rollback_version,
        "artifact": stable.rollback_artifact,
        "trafficPercentage": 100.0,
    }
    if "candidate" in payload["spec"]:
        payload["spec"]["candidate"]["trafficPercentage"] = 0.0


def _rollback_feature(
    payload: dict[str, Any],
    manifest: ModelDeploymentManifest,
    target: dict[str, Any],
) -> None:
    asset_urn = target.get("asset_urn")
    for index, feature in enumerate(manifest.spec.features):
        if feature.asset_urn != asset_urn:
            continue
        if feature.version != target.get("version"):
            raise UnsafeRollback("Feature version does not match the remediation target")
        if feature.rollback_version is None:
            raise UnsafeRollback("Manifest does not declare an explicit feature rollback target")
        payload["spec"]["features"][index]["version"] = feature.rollback_version
        if feature.rollback_configuration is not None:
            payload["spec"]["features"][index]["configuration"] = feature.rollback_configuration
        payload["spec"]["features"][index].pop("rollbackVersion", None)
        payload["spec"]["features"][index].pop("rollbackConfiguration", None)
        return
    raise UnsafeRollback("Feature release is not declared in the deployment manifest")
