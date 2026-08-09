import hashlib
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Protocol, cast

import joblib
import pandas as pd

from demo.runtime.state import RuntimeStateStore
from demo.runtime.types import (
    ComparisonResponse,
    OutcomeRequest,
    PredictionRequest,
    PredictionResponse,
    RuntimeStateView,
)
from histograph.core.time import ensure_utc, utc_now
from histograph.integrations.github.manifest import parse_manifest
from histograph.integrations.github.types import (
    FeatureRelease,
    ModelDeploymentManifest,
    ModelRelease,
)


class ProbabilityModel(Protocol):
    def predict_proba(self, features: pd.DataFrame) -> Any: ...


@dataclass(frozen=True)
class LoadedRelease:
    role: str
    version: str
    artifact: str
    model: ProbabilityModel
    features: tuple[str, ...]
    threshold: float
    traffic_percentage: float


@dataclass(frozen=True)
class ActiveDeployment:
    revision: str
    manifest_content: str
    manifest: ModelDeploymentManifest
    stable: LoadedRelease
    candidate: LoadedRelease | None
    applied_at: datetime


class ReferenceRuntime:
    def __init__(self, workspace_root: Path, state: RuntimeStateStore):
        self._workspace_root = workspace_root.resolve()
        self._state = state
        self._lock = threading.RLock()
        self._active: ActiveDeployment | None = None
        self._restore()

    def apply(
        self, revision: str, content: str, applied_at: datetime | None = None
    ) -> dict[str, Any]:
        timestamp = ensure_utc(applied_at or utc_now())
        manifest = parse_manifest(content)
        if manifest.spec.runtime.provider != "reference":
            raise ValueError(
                "Reference runtime only accepts manifests with runtime.provider=reference"
            )
        stable = self._load_release("stable", manifest.spec.stable)
        candidate = (
            self._load_release("candidate", manifest.spec.candidate)
            if manifest.spec.candidate is not None
            else None
        )
        active = ActiveDeployment(
            revision=revision,
            manifest_content=content,
            manifest=manifest,
            stable=stable,
            candidate=candidate,
            applied_at=timestamp,
        )
        with self._lock:
            previous = self._active
            if previous is not None and previous.revision == revision:
                return self._apply_result(previous, changed=False)
            observed_events = self._observed_events(active, previous)
            self._state.apply_manifest(
                manifest.metadata.name,
                revision,
                content,
                timestamp,
                observed_events,
            )
            self._active = active
        return self._apply_result(active, changed=True)

    def predict(self, request: PredictionRequest) -> PredictionResponse:
        with self._lock:
            active = self._active
        if active is None:
            raise RuntimeError("No deployment manifest has been applied")
        response, telemetry = self._predict(active, request)
        self._state.enqueue("predictions", {"events": [telemetry]}, utc_now())
        return response

    def predict_many(self, requests: list[PredictionRequest]) -> list[PredictionResponse]:
        with self._lock:
            active = self._active
        if active is None:
            raise RuntimeError("No deployment manifest has been applied")
        predictions = [self._predict(active, request) for request in requests]
        self._state.enqueue(
            "predictions",
            {"events": [telemetry for _, telemetry in predictions]},
            utc_now(),
        )
        return [response for response, _ in predictions]

    def compare(self, request: PredictionRequest) -> ComparisonResponse:
        with self._lock:
            active = self._active
        if active is None:
            raise RuntimeError("No deployment manifest has been applied")
        if active.candidate is None:
            raise ValueError("The active deployment has no candidate release to compare")
        stable, _ = self._predict_release(active, request, active.stable)
        candidate, _ = self._predict_release(active, request, active.candidate)
        return ComparisonResponse(stable=stable, candidate=candidate)

    def _predict(
        self, active: ActiveDeployment, request: PredictionRequest
    ) -> tuple[PredictionResponse, dict[str, Any]]:
        release = self._route(active, request.prediction_id)
        return self._predict_release(active, request, release)

    def _predict_release(
        self,
        active: ActiveDeployment,
        request: PredictionRequest,
        release: LoadedRelease,
    ) -> tuple[PredictionResponse, dict[str, Any]]:
        transformed = self._transform_features(request.features, active.manifest.spec.features)
        missing = [name for name in release.features if name not in transformed]
        if missing:
            raise ValueError(f"Prediction is missing required features: {', '.join(missing)}")
        frame = pd.DataFrame([{name: transformed[name] for name in release.features}])
        probabilities = release.model.predict_proba(frame)
        score = float(probabilities[0][1])
        observed_at = ensure_utc(request.observed_at or utc_now())
        positive = active.manifest.spec.model.positive_class
        predicted_class = positive if score >= release.threshold else f"not_{positive}"
        response = PredictionResponse(
            prediction_id=request.prediction_id,
            model=active.manifest.spec.model.name,
            version=release.version,
            deployment=active.manifest.metadata.name,
            score=score,
            predicted_class=predicted_class,
            threshold=release.threshold,
            observed_at=observed_at,
        )
        telemetry = {
            "prediction_id": request.prediction_id,
            "model": response.model,
            "version": response.version,
            "environment": active.manifest.spec.environment,
            "deployment": response.deployment,
            "observed_at": observed_at.isoformat(),
            "predicted_class": predicted_class,
            "score": score,
            "features": transformed,
            "tags": {
                "release_role": release.role,
                "manifest_revision": active.revision,
            },
        }
        return response, telemetry

    def record_outcome(self, outcome: OutcomeRequest) -> None:
        self.record_outcomes([outcome])

    def record_outcomes(self, outcomes: list[OutcomeRequest]) -> None:
        now = utc_now()
        events = []
        for outcome in outcomes:
            observed_at = ensure_utc(outcome.observed_at or now)
            events.append(
                {
                    "prediction_id": outcome.prediction_id,
                    "actual": outcome.actual,
                    "observed_at": observed_at.isoformat(),
                    "metadata": outcome.metadata,
                }
            )
        self._state.enqueue(
            "actuals",
            {"events": events},
            now,
        )

    def view(self) -> RuntimeStateView:
        with self._lock:
            active = self._active
        return RuntimeStateView(
            status="ready" if active is not None else "unconfigured",
            revision=active.revision if active is not None else None,
            manifest=active.manifest if active is not None else None,
            applied_at=active.applied_at if active is not None else None,
            outbox_pending=self._state.pending_count(),
        )

    def _load_release(self, role: str, release: ModelRelease) -> LoadedRelease:
        artifact_path = (self._workspace_root / release.artifact).resolve()
        if not artifact_path.is_relative_to(self._workspace_root):
            raise ValueError("Model artifact must remain within the configured workspace root")
        if not artifact_path.is_file():
            raise FileNotFoundError(f"Model artifact not found: {artifact_path}")
        artifact = joblib.load(artifact_path)
        if not isinstance(artifact, dict):
            raise ValueError(f"Model artifact has an invalid envelope: {artifact_path}")
        model = artifact.get("model")
        features = artifact.get("features")
        if not hasattr(model, "predict_proba"):
            raise ValueError(
                f"Model artifact does not support probability prediction: {artifact_path}"
            )
        if not isinstance(features, list) or not all(
            isinstance(feature, str) and feature for feature in features
        ):
            raise ValueError(f"Model artifact has no valid feature contract: {artifact_path}")
        configured = release.configuration.get("decisionThreshold", artifact.get("threshold"))
        if not isinstance(configured, int | float) or isinstance(configured, bool):
            raise ValueError(f"Release {release.version} has no numeric decision threshold")
        threshold = float(configured)
        if not 0 <= threshold <= 1:
            raise ValueError("Decision threshold must be between zero and one")
        return LoadedRelease(
            role=role,
            version=release.version,
            artifact=release.artifact,
            model=cast(ProbabilityModel, model),
            features=tuple(features),
            threshold=threshold,
            traffic_percentage=release.traffic_percentage,
        )

    def _restore(self) -> None:
        saved = self._state.latest_manifest()
        if saved is None:
            return
        manifest = parse_manifest(str(saved["manifest_content"]))
        applied_at = ensure_utc(datetime.fromisoformat(str(saved["applied_at"])))
        self._active = ActiveDeployment(
            revision=str(saved["revision"]),
            manifest_content=str(saved["manifest_content"]),
            manifest=manifest,
            stable=self._load_release("stable", manifest.spec.stable),
            candidate=(
                self._load_release("candidate", manifest.spec.candidate)
                if manifest.spec.candidate is not None
                else None
            ),
            applied_at=applied_at,
        )

    @staticmethod
    def _route(active: ActiveDeployment, prediction_id: str) -> LoadedRelease:
        candidate = active.candidate
        if candidate is None or candidate.traffic_percentage <= 0:
            return active.stable
        bucket = int.from_bytes(hashlib.sha256(prediction_id.encode()).digest()[:8], "big") % 10_000
        return candidate if bucket < round(candidate.traffic_percentage * 100) else active.stable

    @staticmethod
    def _transform_features(
        features: dict[str, Any], releases: list[FeatureRelease]
    ) -> dict[str, Any]:
        transformed = dict(features)
        for release in releases:
            multiplier = release.configuration.get("scaleMultiplier")
            if multiplier is None:
                continue
            feature_name = release.input_feature
            if feature_name is None:
                raise ValueError(f"Feature {release.name} does not declare inputFeature")
            value = transformed.get(feature_name)
            if not isinstance(multiplier, int | float) or isinstance(multiplier, bool):
                raise ValueError(f"Feature {release.name} scaleMultiplier must be numeric")
            if not isinstance(value, int | float) or isinstance(value, bool):
                raise ValueError(f"Feature {feature_name} must be numeric for scaleMultiplier")
            transformed[feature_name] = value * multiplier
        return transformed

    def _observed_events(
        self, active: ActiveDeployment, previous: ActiveDeployment | None
    ) -> list[tuple[str, dict[str, Any]]]:
        spec = active.manifest.spec
        strategy = "canary" if active.candidate is not None else "standard"
        events: list[tuple[str, dict[str, Any]]] = []
        for release in [active.stable, active.candidate]:
            if release is None:
                continue
            traffic = release.traffic_percentage
            events.append(
                (
                    "deployment",
                    {
                        "deployment": active.manifest.metadata.name,
                        "model": spec.model.name,
                        "version": release.version,
                        "environment": spec.environment,
                        "strategy": strategy,
                        "traffic_percentage": traffic,
                        "status": "active" if traffic > 0 else "stopped",
                        "occurred_at": active.applied_at.isoformat(),
                        "endpoint": spec.runtime.endpoint,
                    },
                )
            )
        previous_features = (
            {item.asset_urn: item for item in previous.manifest.spec.features}
            if previous is not None
            else {}
        )
        for feature in spec.features:
            prior = previous_features.get(feature.asset_urn)
            rolled_back = (
                prior is not None
                and prior.rollback_version is not None
                and prior.rollback_version == feature.version
            )
            events.append(
                (
                    "change",
                    {
                        "asset_urn": feature.asset_urn,
                        "asset_name": feature.name,
                        "asset_type": "feature",
                        "version": feature.version,
                        "environment": spec.environment,
                        "change_type": "rollback" if rolled_back else "configuration",
                        "status": "rolled_back" if rolled_back else "applied",
                        "occurred_at": active.applied_at.isoformat(),
                        "metadata": {
                            "manifest_revision": active.revision,
                            "configuration": feature.configuration,
                            "previous_version": prior.version if prior is not None else None,
                        },
                    },
                )
            )
        return events

    @staticmethod
    def _apply_result(active: ActiveDeployment, *, changed: bool) -> dict[str, Any]:
        return {
            "status": "applied" if changed else "unchanged",
            "deployment": active.manifest.metadata.name,
            "revision": active.revision,
            "applied_at": active.applied_at.isoformat(),
        }
