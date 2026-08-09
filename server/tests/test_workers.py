from datetime import UTC, datetime
from typing import Any, Literal
from uuid import UUID, uuid4

from histograph.detection.service import EvaluationOutcome
from histograph.workers.services import RecoveryEvaluator


class FakeDeploymentStates:
    def __init__(self, state: dict[str, Any] | None):
        self.state = state

    def latest_state(
        self,
        model: str,
        version: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> dict[str, Any] | None:
        assert (model, version, environment, deployment) == (
            "fraud",
            "v2",
            "production",
            "fraud-production",
        )
        return self.state


class FakeChanges:
    def latest(self, asset_urn: str, environment: str = "production") -> dict[str, Any] | None:
        raise AssertionError("Canary recovery must not use upstream change state")


class UnexpectedEvaluation:
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
        raise AssertionError("A stopped canary is verified from deployment state, not stale pairs")


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
    incident = {"monitor_id": uuid4()}
    now = datetime(2026, 8, 9, 12, 0, tzinfo=UTC)
    deployments = FakeDeploymentStates(None)
    evaluator = RecoveryEvaluator(deployments, FakeChanges(), UnexpectedEvaluation())

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
        "occurred_at": now,
    }
    recovery = evaluator.evaluate(action, incident, now)

    assert recovery is not None
    assert [check.name for check in recovery.checks] == [
        "approved_action_execution_succeeded",
        "released_version_traffic_removed",
    ]
