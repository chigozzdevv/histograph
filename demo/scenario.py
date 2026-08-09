import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import duckdb
import httpx
import joblib
import pandas as pd

from demo.datahub_metadata import AMOUNT_FEATURE_URN, MODEL_URN
from demo.statistics import classification_metrics, comparison, population_stability_index
from demo.train import FEATURES


class HistographApi:
    def __init__(self, base_url: str):
        self._client = httpx.Client(base_url=base_url.rstrip("/"), timeout=60)

    def close(self) -> None:
        self._client.close()

    def put(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PUT", path, payload)

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("POST", path, payload)

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self._request("PATCH", path, payload)

    def get(self, path: str) -> dict[str, Any]:
        return self._request("GET", path)

    def _request(
        self, method: str, path: str, payload: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        response = self._client.request(method, path, json=payload)
        if response.is_error:
            raise RuntimeError(
                f"Histograph API {method} {path} returned {response.status_code}: {response.text}"
            )
        body = response.json()
        if not isinstance(body, dict):
            raise RuntimeError(f"Histograph API {method} {path} returned a non-object response")
        return body


def run_feature_release_scenario(
    api_url: str,
    prepared_path: Path,
    artifact_path: Path,
    *,
    sample_size: int = 500,
    investigate: bool = True,
    write_back: bool = False,
    allow_nonviable: bool = False,
) -> dict[str, Any]:
    if write_back and not investigate:
        raise ValueError("DataHub write-back requires investigations to be enabled")
    artifact = _load_artifact(artifact_path)
    manifest = artifact["manifest"]
    if not manifest.get("viable") and not allow_nonviable:
        raise RuntimeError(
            "The trained release scenario did not pass its viability gates. Inspect the model "
            "manifest instead of presenting a weak demo, or pass --allow-nonviable for diagnosis."
        )
    frame = _load_replay_frame(prepared_path, manifest, sample_size)
    model = artifact["model"]
    threshold = float(artifact["threshold"])
    healthy = frame[FEATURES].copy()
    released = healthy.copy()
    released["amount"] = released["amount"] * 100
    actual = frame["is_fraud"].to_numpy()
    healthy_scores = model.predict_proba(healthy)[:, 1]
    released_scores = model.predict_proba(released)[:, 1]
    healthy_metrics = classification_metrics(actual, healthy_scores, threshold)
    released_metrics = classification_metrics(actual, released_scores, threshold)
    performance_metric, operator, degradation = _most_degraded_metric(
        healthy_metrics, released_metrics
    )
    if degradation < 5 and not allow_nonviable:
        raise RuntimeError(
            f"Controlled replay degraded {performance_metric} by only {degradation:.2f}%; "
            "the scenario is not strong enough to present."
        )

    run_id = uuid4().hex[:10]
    model_name = f"mobile-money-fraud-{run_id}"
    deployment = f"mobile-money-fraud-production-{run_id}"
    as_of = datetime.now(UTC).replace(second=0, microsecond=0)
    current_start = as_of - timedelta(minutes=15)
    baseline_start = current_start - timedelta(minutes=60)
    api = HistographApi(api_url)
    try:
        api.put(
            f"/v1/models/{model_name}",
            {
                "name": model_name,
                "task": "binary_classification",
                "positive_class": "fraud",
                "positive_actual": 1,
                "datahub_urn": MODEL_URN,
            },
        )
        api.post(
            "/v1/events/deployments",
            {
                "deployment": deployment,
                "model": model_name,
                "version": "v1",
                "strategy": "standard",
                "traffic_percentage": 100,
                "status": "active",
                "occurred_at": (baseline_start - timedelta(minutes=5)).isoformat(),
            },
        )
        _ingest_phase(
            api,
            run_id,
            "baseline",
            model_name,
            "v1",
            deployment,
            healthy,
            actual,
            healthy_scores,
            threshold,
            baseline_start,
            current_start,
        )
        api.post(
            "/v1/events/changes",
            {
                "asset_urn": AMOUNT_FEATURE_URN,
                "asset_name": "mobile-money-amount-feature",
                "asset_type": "feature",
                "version": "v2",
                "change_type": "configuration",
                "status": "applied",
                "occurred_at": (current_start + timedelta(minutes=1)).isoformat(),
                "metadata": {
                    "changed_features": ["amount"],
                    "scale_multiplier_before": 1,
                    "scale_multiplier_after": 100,
                    "release_id": f"feature-release-{run_id}",
                },
            },
        )
        _ingest_phase(
            api,
            run_id,
            "released",
            model_name,
            "v1",
            deployment,
            released,
            actual,
            released_scores,
            threshold,
            current_start,
            as_of,
        )
        minimum_sample_size = min(100, len(frame))
        feature_monitor = api.post(
            "/v1/monitors",
            {
                "model": model_name,
                "version": "v1",
                "deployment": deployment,
                "signal": "feature_drift",
                "metric": "psi",
                "operator": "gt",
                "threshold": 0.2,
                "baseline_window_minutes": 60,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": minimum_sample_size,
            },
        )
        performance_monitor = api.post(
            "/v1/monitors",
            {
                "model": model_name,
                "version": "v1",
                "deployment": deployment,
                "signal": "performance",
                "metric": performance_metric,
                "operator": operator,
                "threshold": 0.05,
                "baseline_window_minutes": 60,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": minimum_sample_size,
            },
        )
        feature_detection = api.post(
            f"/v1/detection/monitors/{feature_monitor['id']}/feature-drift",
            {"feature": "amount", "as_of": as_of.isoformat()},
        )
        performance_detection = api.post(
            f"/v1/detection/monitors/{performance_monitor['id']}/performance",
            {"as_of": as_of.isoformat()},
        )
        _require_trigger("feature drift", feature_detection)
        _require_trigger("performance degradation", performance_detection)
        feature_incident_id = str(feature_detection["incident_id"])
        performance_incident_id = str(performance_detection["incident_id"])
        investigation_before = (
            api.post(f"/v1/investigations/{feature_incident_id}", {"max_hops": 3})
            if investigate
            else None
        )

        rollback_at = as_of + timedelta(minutes=2)
        api.post(
            "/v1/events/changes",
            {
                "asset_urn": AMOUNT_FEATURE_URN,
                "asset_name": "mobile-money-amount-feature",
                "asset_type": "feature",
                "version": "v1",
                "change_type": "rollback",
                "status": "rolled_back",
                "occurred_at": rollback_at.isoformat(),
                "metadata": {
                    "changed_features": ["amount"],
                    "restored_scale_multiplier": 1,
                    "rolls_back": f"feature-release-{run_id}",
                },
            },
        )
        recovery_as_of = as_of + timedelta(minutes=20)
        _ingest_phase(
            api,
            run_id,
            "recovery",
            model_name,
            "v1",
            deployment,
            healthy,
            actual,
            healthy_scores,
            threshold,
            recovery_as_of - timedelta(minutes=15),
            recovery_as_of,
        )
        recovery_detection = api.post(
            f"/v1/detection/monitors/{performance_monitor['id']}/performance",
            {"as_of": recovery_as_of.isoformat()},
        )
        if recovery_detection["status"] != "evaluated" or recovery_detection["triggered"]:
            raise RuntimeError("Recovery performance monitor did not pass")
        recovery = {
            "status": "verified",
            "verified_at": recovery_as_of.isoformat(),
            "checks": [
                {
                    "name": "directional_performance_monitor_passed",
                    "passed": True,
                    "details": {
                        "metric": performance_metric,
                        "observed": recovery_detection["observed_value"],
                        "comparison": recovery_detection["comparison"],
                    },
                },
                {
                    "name": "controlled_replay_restored",
                    "passed": True,
                    "details": {
                        "rows": len(frame),
                        "healthy": healthy_metrics,
                        "released": released_metrics,
                    },
                },
            ],
        }
        for incident_id in {feature_incident_id, performance_incident_id}:
            api.post(f"/v1/incidents/{incident_id}/recovery", recovery)
        investigation_after = (
            api.post(
                f"/v1/investigations/{feature_incident_id}",
                {"max_hops": 3, "write_back": write_back},
            )
            if investigate
            else None
        )
        for incident_id in {feature_incident_id, performance_incident_id}:
            api.patch(f"/v1/incidents/{incident_id}", {"status": "resolved"})
        final_incident = api.get(f"/v1/incidents/{feature_incident_id}")
    finally:
        api.close()

    return {
        "scenario": "silent_feature_unit_change",
        "run_id": run_id,
        "model": model_name,
        "registered_datahub_urn": MODEL_URN,
        "release": {
            "asset_urn": AMOUNT_FEATURE_URN,
            "feature": "amount",
            "scale_multiplier_before": 1,
            "scale_multiplier_after": 100,
        },
        "controlled_replay": {
            "rows_per_phase": len(frame),
            "same_rows_before_and_after": True,
            "healthy_metrics": healthy_metrics,
            "released_metrics": released_metrics,
            "performance_comparison": comparison(
                float(healthy_metrics[performance_metric]),
                float(released_metrics[performance_metric]),
                lower_is_better=performance_metric == "false_positive_rate",
            ),
            "feature_psi": population_stability_index(
                healthy["amount"].to_numpy(), released["amount"].to_numpy()
            ),
        },
        "detections": {
            "feature": feature_detection,
            "performance": performance_detection,
            "recovery": recovery_detection,
        },
        "incidents": {
            "feature": feature_incident_id,
            "performance": performance_incident_id,
            "final_status": final_incident["status"],
        },
        "causality": {
            "controlled_input": True,
            "release_preceded_signal": True,
            "datahub_enabled": investigate,
            "before_rollback": investigation_before,
            "after_verified_rollback": investigation_after,
            "claim": (
                "confirmed only after lineage match, rollback, controlled replay recovery, "
                "and persisted verification"
                if investigate
                else "not attributed because the DataHub investigation was skipped"
            ),
        },
    }


def run_model_canary_scenario(
    api_url: str,
    prepared_path: Path,
    artifact_path: Path,
    *,
    sample_size: int = 500,
    investigate: bool = True,
    write_back: bool = False,
) -> dict[str, Any]:
    if write_back and not investigate:
        raise ValueError("DataHub write-back requires investigations to be enabled")
    artifact = _load_artifact(artifact_path)
    frame = _load_replay_frame(prepared_path, artifact["manifest"], sample_size)
    model = artifact["model"]
    reference_threshold = float(artifact["threshold"])
    candidate_threshold = min(0.99, reference_threshold + 0.20)
    scores = model.predict_proba(frame[FEATURES])[:, 1]
    actual = frame["is_fraud"].to_numpy()
    reference_metrics = classification_metrics(actual, scores, reference_threshold)
    candidate_metrics = classification_metrics(actual, scores, candidate_threshold)
    degradation = comparison(float(reference_metrics["recall"]), float(candidate_metrics["recall"]))
    if float(degradation["degradation_percent"]) < 5:
        raise RuntimeError("The canary threshold mutation did not produce a useful recall loss")

    run_id = uuid4().hex[:10]
    model_name = f"mobile-money-fraud-canary-{run_id}"
    deployment = f"mobile-money-fraud-production-{run_id}"
    as_of = datetime.now(UTC).replace(second=0, microsecond=0)
    start = as_of - timedelta(minutes=15)
    api = HistographApi(api_url)
    try:
        api.put(
            f"/v1/models/{model_name}",
            {
                "name": model_name,
                "task": "binary_classification",
                "positive_class": "fraud",
                "positive_actual": 1,
                "datahub_urn": MODEL_URN,
            },
        )
        for version, traffic, status in (("v1", 90, "active"), ("v2", 10, "monitoring")):
            api.post(
                "/v1/events/deployments",
                {
                    "deployment": deployment,
                    "model": model_name,
                    "version": version,
                    "strategy": "canary",
                    "traffic_percentage": traffic,
                    "status": status,
                    "occurred_at": (start - timedelta(minutes=2)).isoformat(),
                    "endpoint": f"demo://{deployment}/{version}",
                },
            )
        _ingest_phase(
            api,
            run_id,
            "reference",
            model_name,
            "v1",
            deployment,
            frame[FEATURES],
            actual,
            scores,
            reference_threshold,
            start,
            as_of,
        )
        _ingest_phase(
            api,
            run_id,
            "candidate",
            model_name,
            "v2",
            deployment,
            frame[FEATURES],
            actual,
            scores,
            candidate_threshold,
            start,
            as_of,
        )
        monitor = api.post(
            "/v1/monitors",
            {
                "model": model_name,
                "version": "v2",
                "deployment": deployment,
                "signal": "performance",
                "metric": "recall",
                "operator": "decrease",
                "threshold": 0.05,
                "evaluation_window_minutes": 15,
                "minimum_sample_size": min(100, len(frame)),
            },
        )
        detection = api.post(
            f"/v1/detection/monitors/{monitor['id']}/performance",
            {"as_of": as_of.isoformat(), "reference_version": "v1"},
        )
        _require_trigger("same-window canary degradation", detection)
        incident_id = str(detection["incident_id"])
        investigation_before = (
            api.post(f"/v1/investigations/{incident_id}", {"max_hops": 3}) if investigate else None
        )
        rollback_at = as_of + timedelta(minutes=2)
        api.post(
            "/v1/events/deployments",
            {
                "deployment": deployment,
                "model": model_name,
                "version": "v2",
                "strategy": "canary",
                "traffic_percentage": 0,
                "status": "rolled_back",
                "occurred_at": rollback_at.isoformat(),
                "endpoint": f"demo://{deployment}/v2",
            },
        )
        api.post(
            f"/v1/incidents/{incident_id}/recovery",
            {
                "status": "verified",
                "verified_at": (rollback_at + timedelta(minutes=1)).isoformat(),
                "checks": [
                    {
                        "name": "candidate_traffic_removed",
                        "passed": True,
                        "details": {
                            "candidate_version": "v2",
                            "traffic_percentage": 0,
                            "reference_version": "v1",
                        },
                    }
                ],
            },
        )
        investigation_after = (
            api.post(
                f"/v1/investigations/{incident_id}",
                {"max_hops": 3, "write_back": write_back},
            )
            if investigate
            else None
        )
        api.patch(f"/v1/incidents/{incident_id}", {"status": "resolved"})
    finally:
        api.close()

    return {
        "scenario": "model_canary_threshold_regression",
        "run_id": run_id,
        "model": model_name,
        "reference": {"version": "v1", "threshold": reference_threshold},
        "candidate": {"version": "v2", "threshold": candidate_threshold},
        "controlled_replay": {
            "same_rows_and_scores": True,
            "reference_metrics": reference_metrics,
            "candidate_metrics": candidate_metrics,
        },
        "detection": detection,
        "incident_id": incident_id,
        "investigation_before_rollback": investigation_before,
        "investigation_after_verified_rollback": investigation_after,
        "final_status": "resolved",
    }


def _load_artifact(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Model artifact not found: {path}")
    artifact = joblib.load(path)
    if not isinstance(artifact, dict) or not {"model", "threshold", "manifest"} <= set(artifact):
        raise ValueError("Model artifact does not match the Histograph demo contract")
    return artifact


def _load_replay_frame(path: Path, manifest: dict[str, Any], sample_size: int) -> pd.DataFrame:
    if sample_size < 100:
        raise ValueError("Scenario sample size must be at least 100")
    test_start = float(manifest["split_boundaries"]["test_start"])
    connection = duckdb.connect()
    try:
        frame = connection.execute(
            """
            SELECT * FROM read_parquet(?)
            WHERE step >= ?
            ORDER BY hash(step, initiator, recipient, amount)
            LIMIT ?
            """,
            [str(path), test_start, sample_size],
        ).fetch_df()
    finally:
        connection.close()
    if len(frame) < sample_size:
        raise ValueError(f"Prepared test partition has {len(frame)} rows, need {sample_size}")
    return frame


def _most_degraded_metric(
    healthy: dict[str, float | int], released: dict[str, float | int]
) -> tuple[str, str, float]:
    candidates = {
        "recall": comparison(float(healthy["recall"]), float(released["recall"])),
        "f1": comparison(float(healthy["f1"]), float(released["f1"])),
        "false_positive_rate": comparison(
            float(healthy["false_positive_rate"]),
            float(released["false_positive_rate"]),
            lower_is_better=True,
        ),
    }
    metric = max(candidates, key=lambda name: float(candidates[name]["degradation_percent"]))
    operator = "increase" if metric == "false_positive_rate" else "decrease"
    return metric, operator, float(candidates[metric]["degradation_percent"])


def _ingest_phase(
    api: HistographApi,
    run_id: str,
    phase: str,
    model_name: str,
    version: str,
    deployment: str,
    features: pd.DataFrame,
    actual: Any,
    scores: Any,
    threshold: float,
    start: datetime,
    end: datetime,
) -> None:
    seconds = (end - start).total_seconds()
    predictions = []
    actuals = []
    for offset, ((_, row), score, label) in enumerate(
        zip(features.iterrows(), scores, actual, strict=True)
    ):
        observed_at = start + timedelta(seconds=seconds * (offset + 0.25) / len(features))
        prediction_id = f"{run_id}-{phase}-{offset}"
        predictions.append(
            {
                "prediction_id": prediction_id,
                "model": model_name,
                "version": version,
                "deployment": deployment,
                "observed_at": observed_at.isoformat(),
                "predicted_class": "fraud" if float(score) >= threshold else "legitimate",
                "score": float(score),
                "features": {feature: _scalar(row[feature]) for feature in FEATURES},
                "tags": {"scenario_phase": phase, "controlled_replay": "true"},
            }
        )
        actuals.append(
            {
                "prediction_id": prediction_id,
                "actual": int(label),
                "observed_at": (observed_at + timedelta(seconds=1)).isoformat(),
                "metadata": {"label_delay_seconds": 1, "scenario_phase": phase},
            }
        )
    for batch in _batches(predictions):
        api.post("/v1/events/predictions/batch", {"events": batch})
    for batch in _batches(actuals):
        api.post("/v1/events/actuals/batch", {"events": batch})


def _batches(events: list[dict[str, Any]], size: int = 1000) -> list[list[dict[str, Any]]]:
    return [events[offset : offset + size] for offset in range(0, len(events), size)]


def _scalar(value: Any) -> bool | int | float | str | None:
    if value is None or pd.isna(value):
        return None
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, bool | int | float | str):
        return value
    return str(value)


def _require_trigger(name: str, detection: dict[str, Any]) -> None:
    if detection.get("status") != "evaluated" or detection.get("triggered") is not True:
        raise RuntimeError(
            f"Expected {name} to trigger, received:\n{json.dumps(detection, indent=2)}"
        )
