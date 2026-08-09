import asyncio
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID

from histograph.agents.investigation.agent import InvestigationAgent
from histograph.core.time import ensure_utc
from histograph.detection.service import EvaluationOutcome
from histograph.incidents.service import IncidentService
from histograph.incidents.types import IncidentTransition, RecoveryVerification
from histograph.monitors.types import MonitorEvent
from histograph.remediation.adapters import RemediationAdapter
from histograph.remediation.service import RemediationService
from histograph.remediation.types import ExecutionResult

logger = logging.getLogger(__name__)


class ScheduledMonitorStore(Protocol):
    def claim_due(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def complete_evaluation(
        self,
        monitor_id: UUID,
        scheduled_for: datetime,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None: ...

    def fail_evaluation(
        self,
        monitor_id: UUID,
        scheduled_for: datetime,
        failed_at: datetime,
        error: str,
        retry_seconds: int,
    ) -> None: ...


class InvestigationStore(Protocol):
    def create(self, event: MonitorEvent, summary: str, evidence: dict[str, Any]) -> UUID: ...

    def claim_investigations(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def get(self, incident_id: UUID) -> dict[str, Any] | None: ...

    def get_with_monitor(self, incident_id: UUID) -> dict[str, Any] | None: ...

    def complete_investigation(self, incident_id: UUID) -> None: ...

    def fail_investigation(
        self, incident_id: UUID, failed_at: datetime, error: str, retry_seconds: int
    ) -> None: ...

    def record_recovery(
        self, incident_id: UUID, recovery: RecoveryVerification
    ) -> dict[str, Any] | None: ...

    def transition(
        self, incident_id: UUID, status: str, reason: str | None
    ) -> dict[str, Any] | None: ...

    def update(self, incident_id: UUID, summary: str, evidence: dict[str, Any]) -> bool: ...


class ModelStore(Protocol):
    def get(self, name: str) -> dict[str, Any] | None: ...


class ActionStore(Protocol):
    def claim_approved(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def complete_execution(
        self, action_id: UUID, result: ExecutionResult, completed_at: datetime | None = None
    ) -> dict[str, Any] | None: ...

    def fail_execution(
        self, action_id: UUID, error: str, failed_at: datetime | None = None
    ) -> None: ...

    def claim_recovery_due(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def reschedule_recovery(self, action_id: UUID, when: datetime, error: str | None) -> None: ...

    def mark_recovery_verified(self, action_id: UUID, verified_at: datetime) -> None: ...

    def cancel_for_incident(self, incident_id: UUID, reason: str) -> int: ...


class DeploymentStateStore(Protocol):
    def latest_state(
        self,
        model: str,
        version: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> dict[str, Any] | None: ...


class ChangeStateStore(Protocol):
    def latest(self, asset_urn: str, environment: str = "production") -> dict[str, Any] | None: ...


class EvaluationService(Protocol):
    def evaluate(
        self,
        monitor_id: UUID,
        as_of: datetime,
        *,
        feature: str | None = None,
        reference_version: str | None = None,
        expected_signal: Literal["performance", "feature_drift"] | None = None,
        persist: bool = True,
    ) -> EvaluationOutcome: ...


class MonitorWorker:
    def __init__(
        self,
        worker_id: str,
        schedules: ScheduledMonitorStore,
        evaluation: EvaluationService,
        *,
        batch_size: int,
        lease_seconds: int,
        retry_seconds: int,
    ):
        self._worker_id = worker_id
        self._schedules = schedules
        self._evaluation = evaluation
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds

    def run_once(self, now: datetime) -> int:
        timestamp = ensure_utc(now)
        records = self._schedules.claim_due(
            self._worker_id, timestamp, self._batch_size, self._lease_seconds
        )
        for record in records:
            monitor_id = record["id"]
            scheduled_for = record["next_evaluation_at"]
            try:
                outcome = self._evaluation.evaluate(monitor_id, timestamp)
                self._schedules.complete_evaluation(
                    monitor_id, scheduled_for, timestamp, outcome.as_dict()
                )
            except Exception as error:
                logger.exception("monitor evaluation failed", extra={"monitor_id": str(monitor_id)})
                self._schedules.fail_evaluation(
                    monitor_id,
                    scheduled_for,
                    timestamp,
                    str(error),
                    self._retry_seconds,
                )
        return len(records)


class InvestigationWorker:
    def __init__(
        self,
        worker_id: str,
        incidents: InvestigationStore,
        models: ModelStore,
        datahub,
        release_context,
        remediation: RemediationService,
        *,
        batch_size: int,
        lease_seconds: int,
        retry_seconds: int,
    ):
        self._worker_id = worker_id
        self._incidents = incidents
        self._models = models
        self._datahub = datahub
        self._release_context = release_context
        self._remediation = remediation
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds

    async def run_once(self, now: datetime) -> int:
        timestamp = ensure_utc(now)
        records = self._incidents.claim_investigations(
            self._worker_id, timestamp, self._batch_size, self._lease_seconds
        )
        for incident in records:
            incident_id = incident["id"]
            try:
                model_urn = _model_urn(self._models, incident)
                if incident["status"] == "open":
                    IncidentService(self._incidents).transition(
                        incident_id, IncidentTransition(status="investigating")
                    )
                agent = InvestigationAgent(self._incidents, self._datahub, self._release_context)
                report = await agent.investigate(incident_id, model_urn, max_hops=3)
                current = self._incidents.get(incident_id)
                if current is None:
                    raise RuntimeError("Incident disappeared during investigation")
                self._remediation.propose_from_investigation(current, report)
                self._incidents.complete_investigation(incident_id)
            except Exception as error:
                logger.exception(
                    "incident investigation failed", extra={"incident_id": str(incident_id)}
                )
                self._incidents.fail_investigation(
                    incident_id, timestamp, str(error), self._retry_seconds
                )
        return len(records)


class ActionWorker:
    def __init__(
        self,
        worker_id: str,
        actions: ActionStore,
        adapters: dict[str, RemediationAdapter],
        *,
        batch_size: int,
        lease_seconds: int,
    ):
        self._worker_id = worker_id
        self._actions = actions
        self._adapters = adapters
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds

    async def run_once(self, now: datetime) -> int:
        timestamp = ensure_utc(now)
        records = self._actions.claim_approved(
            self._worker_id,
            timestamp,
            self._batch_size,
            self._lease_seconds,
        )
        for action in records:
            action_id = action["id"]
            adapter = self._adapters.get(action["adapter"])
            if adapter is None:
                self._actions.fail_execution(
                    action_id,
                    f"No configured remediation adapter named {action['adapter']}",
                    timestamp,
                )
                continue
            try:
                result = await adapter.execute(action)
                self._actions.complete_execution(action_id, result, timestamp)
            except Exception as error:
                logger.exception(
                    "remediation execution failed", extra={"action_id": str(action_id)}
                )
                self._actions.fail_execution(action_id, str(error), timestamp)
        return len(records)


class RecoveryEvaluator:
    def __init__(
        self,
        deployments: DeploymentStateStore,
        changes: ChangeStateStore,
        evaluation: EvaluationService,
    ):
        self._deployments = deployments
        self._changes = changes
        self._evaluation = evaluation

    def evaluate(
        self, action: dict[str, Any], incident: dict[str, Any], now: datetime
    ) -> RecoveryVerification | None:
        target = action.get("target")
        if not isinstance(target, dict):
            raise ValueError("Remediation action has no structured target")
        checks: list[dict[str, Any]] = [
            {
                "name": "approved_action_execution_succeeded",
                "passed": True,
                "details": {
                    "action_id": str(action["id"]),
                    "external_execution_id": action.get("external_execution_id"),
                },
            }
        ]
        if action["action_type"] in {"stop_canary", "rollback_model"}:
            state = self._deployment_state(target)
            if state is None or not _state_follows_execution(action, state):
                return None
            removed = (
                state.get("status") in {"stopped", "rolled_back"}
                and float(state.get("traffic_percentage", -1)) == 0
            )
            if not removed:
                return None
            checks.append(
                {
                    "name": "released_version_traffic_removed",
                    "passed": True,
                    "details": {
                        "status": state.get("status"),
                        "traffic_percentage": state.get("traffic_percentage"),
                        "occurred_at": state.get("occurred_at"),
                    },
                }
            )
        elif action["action_type"] == "rollback_release":
            asset_urn = target.get("asset_urn")
            if not isinstance(asset_urn, str):
                raise ValueError("Release rollback action has no asset URN")
            state = self._changes.latest(asset_urn, _environment(target))
            if (
                state is None
                or not (
                    state.get("status") == "rolled_back" or state.get("change_type") == "rollback"
                )
                or not _state_follows_execution(action, state)
            ):
                return None
            monitor_id = incident.get("monitor_id")
            if not isinstance(monitor_id, UUID):
                raise ValueError("Incident is not linked to a monitor")
            outcome = self._evaluation.evaluate(monitor_id, ensure_utc(now), persist=False)
            if outcome.result.status != "evaluated" or outcome.result.triggered:
                return None
            checks.extend(
                [
                    {
                        "name": "upstream_release_rolled_back",
                        "passed": True,
                        "details": {
                            "asset_urn": asset_urn,
                            "version": state.get("version"),
                            "occurred_at": state.get("occurred_at"),
                        },
                    },
                    {
                        "name": "fresh_monitor_window_passed",
                        "passed": True,
                        "details": outcome.as_dict(),
                    },
                ]
            )
        else:
            raise ValueError(f"Unsupported remediation action type: {action['action_type']}")
        return RecoveryVerification.model_validate(
            {"status": "verified", "verified_at": ensure_utc(now), "checks": checks}
        )

    def _deployment_state(self, target: dict[str, Any]) -> dict[str, Any] | None:
        model = target.get("model")
        version = target.get("version")
        if not isinstance(model, str) or not isinstance(version, str):
            raise ValueError("Model remediation target requires model and version")
        deployment = target.get("deployment")
        return self._deployments.latest_state(
            model,
            version,
            _environment(target),
            deployment if isinstance(deployment, str) else None,
        )


class RecoveryWorker:
    def __init__(
        self,
        worker_id: str,
        actions: ActionStore,
        incidents: InvestigationStore,
        models: ModelStore,
        datahub,
        release_context,
        evaluator: RecoveryEvaluator,
        *,
        write_back: bool,
        batch_size: int,
        lease_seconds: int,
        retry_seconds: int,
    ):
        self._worker_id = worker_id
        self._actions = actions
        self._incidents = incidents
        self._models = models
        self._datahub = datahub
        self._release_context = release_context
        self._evaluator = evaluator
        self._write_back = write_back
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds
        self._retry_seconds = retry_seconds

    async def run_once(self, now: datetime) -> int:
        timestamp = ensure_utc(now)
        records = self._actions.claim_recovery_due(
            self._worker_id, timestamp, self._batch_size, self._lease_seconds
        )
        for action in records:
            action_id = action["id"]
            try:
                incident = self._incidents.get_with_monitor(action["incident_id"])
                if incident is None:
                    raise RuntimeError("Remediation incident no longer exists")
                recovery = self._evaluator.evaluate(action, incident, timestamp)
                if recovery is None:
                    self._retry(action_id, timestamp, None)
                    continue
                IncidentService(self._incidents).record_recovery(incident["id"], recovery)
                model_urn = _model_urn(self._models, incident)
                report = await InvestigationAgent(
                    self._incidents, self._datahub, self._release_context
                ).investigate(
                    incident["id"],
                    model_urn,
                    max_hops=3,
                    write_back=self._write_back and not _has_datahub_writeback(incident),
                )
                if report.get("status") != "confirmed_cause":
                    self._retry(
                        action_id,
                        timestamp,
                        "Recovery passed but causal confirmation is not complete",
                    )
                    continue
                IncidentService(self._incidents).transition(
                    incident["id"], IncidentTransition(status="resolved")
                )
                self._actions.cancel_for_incident(
                    incident["id"], "Incident reached verified resolution"
                )
                self._incidents.complete_investigation(incident["id"])
                self._actions.mark_recovery_verified(action_id, recovery.verified_at)
            except Exception as error:
                logger.exception(
                    "recovery verification failed", extra={"action_id": str(action_id)}
                )
                self._retry(action_id, timestamp, str(error))
        return len(records)

    def _retry(self, action_id: UUID, now: datetime, error: str | None) -> None:
        self._actions.reschedule_recovery(
            action_id, ensure_utc(now) + timedelta(seconds=self._retry_seconds), error
        )


class ControlPlaneWorker:
    def __init__(
        self,
        monitor: MonitorWorker,
        investigation: InvestigationWorker,
        action: ActionWorker,
        recovery: RecoveryWorker,
        gitops=None,
        demo=None,
    ):
        self._monitor = monitor
        self._investigation = investigation
        self._action = action
        self._recovery = recovery
        self._gitops = gitops
        self._demo = demo

    async def run_once(self, now: datetime) -> dict[str, int]:
        counts = {
            "demo": await self._demo.run_once(now) if self._demo is not None else 0,
            "monitors": self._monitor.run_once(now),
            "investigations": await self._investigation.run_once(now),
        }
        counts["gitops"] = await self._gitops.run_once(now) if self._gitops is not None else 0
        counts["actions"] = await self._action.run_once(now)
        counts["recoveries"] = await self._recovery.run_once(now)
        return counts

    async def run_forever(
        self, clock: Callable[[], datetime], poll_interval_seconds: float
    ) -> None:
        while True:
            try:
                counts = await self.run_once(clock())
                if any(counts.values()):
                    logger.info("control-plane worker tick completed", extra={"counts": counts})
            except Exception:
                logger.exception("control-plane worker tick failed")
            await asyncio.sleep(poll_interval_seconds)


def _model_urn(models: ModelStore, incident: dict[str, Any]) -> str:
    model_name = incident.get("model")
    if not isinstance(model_name, str):
        raise ValueError("Incident does not identify a registered model")
    model = models.get(model_name)
    if model is None:
        raise ValueError("Incident model is not registered")
    model_urn = model.get("datahub_urn")
    if not isinstance(model_urn, str) or not model_urn.strip():
        raise ValueError("Registered model has no DataHub URN")
    return model_urn


def _environment(target: dict[str, Any]) -> str:
    environment = target.get("environment")
    return environment if isinstance(environment, str) else "production"


def _has_datahub_writeback(incident: dict[str, Any]) -> bool:
    evidence = incident.get("evidence")
    datahub = evidence.get("datahub") if isinstance(evidence, dict) else None
    return isinstance(datahub, dict) and datahub.get("writeback") is not None


def _state_follows_execution(action: dict[str, Any], state: dict[str, Any]) -> bool:
    execution_started_at = _timestamp(action.get("execution_started_at"))
    state_occurred_at = _timestamp(state.get("occurred_at"))
    return (
        execution_started_at is not None
        and state_occurred_at is not None
        and state_occurred_at >= execution_started_at
    )


def _timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return ensure_utc(value)
    if isinstance(value, str):
        try:
            return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
        except ValueError:
            return None
    return None
