from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from histograph.detection.engine import DetectionResult
from histograph.detection.service import EvaluationOutcome
from histograph.monitors.types import Monitor
from histograph.workers.services import RecoveryEvaluator


class FakeDeploymentStates:
    def __init__(self, state: dict[str, Any] | None):
        self.state = state
        self.active: list[dict[str, Any]] = []
        self.target_version = "v2"

    def active_versions(
        self,
        model: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> list[dict[str, Any]]:
        assert (model, environment, deployment) == (
            "fraud",
            "production",
            "fraud-production",
        )
        return self.active

    def latest_state(
        self,
        model: str,
        version: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> dict[str, Any] | None:
        assert (model, version, environment, deployment) == (
            "fraud",
            self.target_version,
            "production",
            "fraud-production",
        )
        return self.state


class FakeChanges:
    def latest(self, asset_urn: str, environment: str = "production") -> dict[str, Any] | None:
        raise AssertionError("Canary recovery must not use upstream change state")


class RecoveryEvaluation:
    def __init__(self) -> None:
        self.status: Literal["evaluated", "insufficient_data"] = "insufficient_data"
        self.triggered = False
        self.calls: list[tuple[Any, ...]] = []

    def evaluate(
        self,
        monitor_id: UUID,
        as_of: datetime,
        *,
        feature: str | None = None,
        reference_version: str | None = None,
        expected_signal: Literal["performance", "feature_drift"] | None = None,
        persist: bool = True,
    ) -> EvaluationOutcome:
        raise AssertionError("Canary recovery must use the post-remediation evaluator")

    def evaluate_recovery(
        self,
        monitor_id: UUID,
        recovery_version: str,
        not_before: datetime,
        as_of: datetime,
        baseline_value: float,
    ) -> EvaluationOutcome:
        self.calls.append((monitor_id, recovery_version, not_before, as_of, baseline_value))
        return EvaluationOutcome(
            monitor=Monitor(
                model="fraud",
                version="v2",
                reference_version="v1",
                signal="performance",
                metric="recall",
                operator="decrease",
                threshold=0.2,
            ),
            result=DetectionResult(
                status=self.status,
                triggered=self.triggered,
                metric="recall",
                observed_value=1.0 if self.status == "evaluated" else None,
                baseline_value=1.0,
                threshold=0.2,
                sample_size=4 if self.status == "evaluated" else 0,
                comparison={},
                evidence={"window": {}},
            ),
            incident_id=None,
        )


def test_executor_success_alone_does_not_verify_canary_recovery() -> None:
    action = {
        "id": uuid4(),
        "action_type": "stop_canary",
        "external_execution_id": "provider-123",
        "execution_started_at": datetime(2026, 8, 9, 11, 59, tzinfo=UTC),
        "target": {
            "model": "fraud",
            "version": "v2",
            "deployment": "fraud-production",
            "environment": "production",
        },
    }
    monitor_id = uuid4()
    incident = {
        "monitor_id": monitor_id,
        "evidence": {
            "trigger": {"baseline_value": 1.0},
            "detection": {"reference": {"version": "v1"}},
        },
    }
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
    deployments = FakeDeploymentStates(None)
    evaluation = RecoveryEvaluation()
    evaluator = RecoveryEvaluator(deployments, FakeChanges(), evaluation)

    assert evaluator.evaluate(action, incident, now) is None
    deployments.state = {
        "status": "monitoring",
        "traffic_percentage": 10,
        "occurred_at": now,
    }
    assert evaluator.evaluate(action, incident, now) is None

    deployments.state = {
        "status": "rolled_back",
        "traffic_percentage": 0,
        "occurred_at": datetime(2026, 8, 9, 11, 58, tzinfo=UTC),
    }
    assert evaluator.evaluate(action, incident, now) is None

    deployments.state = {
        "status": "rolled_back",
        "traffic_percentage": 0,
        "occurred_at": datetime(2026, 8, 9, 11, 59, 30, tzinfo=UTC),
    }
    assert evaluator.evaluate(action, incident, now) is None
    evaluation.status = "evaluated"
    evaluation.triggered = True
    assert evaluator.evaluate(action, incident, now) is None
    evaluation.triggered = False
    recovery = evaluator.evaluate(action, incident, now)

    assert recovery is not None
    assert [check.name for check in recovery.checks] == [
        "approved_action_execution_succeeded",
        "released_version_traffic_removed",
        "fresh_performance_window_passed",
    ]
    assert evaluation.calls[-1] == (
        monitor_id,
        "v1",
        datetime(2026, 8, 9, 11, 59, 30, tzinfo=UTC),
        now,
        1.0,
    )


def test_model_rollback_verifies_fresh_traffic_on_the_new_active_version() -> None:
    applied_at = datetime(2026, 8, 9, 11, 59, 30, tzinfo=UTC)
    deployments = FakeDeploymentStates(
        {"status": "stopped", "traffic_percentage": 0, "occurred_at": applied_at}
    )
    deployments.target_version = "v1"
    deployments.active = [
        {
            "version": "v0",
            "status": "active",
            "traffic_percentage": 100,
            "occurred_at": applied_at,
        }
    ]
    evaluation = RecoveryEvaluation()
    evaluation.status = "evaluated"
    evaluator = RecoveryEvaluator(deployments, FakeChanges(), evaluation)
    monitor_id = uuid4()
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)

    recovery = evaluator.evaluate(
        {
            "id": uuid4(),
            "action_type": "rollback_model",
            "external_execution_id": "provider-456",
            "execution_started_at": datetime(2026, 8, 9, 11, 59, tzinfo=UTC),
            "target": {
                "model": "fraud",
                "version": "v1",
                "deployment": "fraud-production",
                "environment": "production",
            },
        },
        {"monitor_id": monitor_id, "evidence": {"trigger": {"baseline_value": 1.0}}},
        now,
    )

    assert recovery is not None
    assert evaluation.calls[-1] == (monitor_id, "v0", applied_at, now, 1.0)
