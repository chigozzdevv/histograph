from typing import Any, Protocol
from uuid import UUID

from histograph.incidents.types import IncidentTransition
from histograph.monitors.types import MonitorEvent


class IncidentStore(Protocol):
    def create(self, event: MonitorEvent, summary: str, evidence: dict[str, Any]) -> UUID: ...

    def get(self, incident_id: UUID) -> dict[str, Any] | None: ...

    def transition(
        self, incident_id: UUID, status: str, reason: str | None
    ) -> dict[str, Any] | None: ...


class IncidentService:
    def __init__(self, repository: IncidentStore):
        self._repository = repository

    def create_from_monitor_event(
        self, event: MonitorEvent, detection_evidence: dict[str, Any]
    ) -> UUID:
        observed = event.observed_value
        baseline = "unavailable" if event.baseline_value is None else f"{event.baseline_value:.6f}"
        summary = (
            f"{event.metric} crossed its threshold for {event.model} {event.version}: "
            f"observed {observed:.6f}, baseline {baseline}, threshold {event.threshold:.6f}."
        )
        evidence = {
            "trigger": event.model_dump(mode="json"),
            "detection": detection_evidence,
            "root_cause_status": "uninvestigated",
            "hypotheses": [],
            "datahub": {"status": "pending_investigation"},
        }
        return self._repository.create(event, summary, evidence)

    def transition(
        self,
        incident_id: UUID,
        transition: IncidentTransition,
    ) -> dict[str, Any] | None:
        current = self._repository.get(incident_id)
        if current is None:
            return None

        allowed = {
            "open": {"investigating", "resolved", "closed"},
            "investigating": {"open", "resolved", "closed"},
            "resolved": {"open", "closed"},
            "closed": {"open"},
        }
        current_status = current["status"]
        if transition.status == current_status:
            return current
        if transition.status not in allowed.get(current_status, set()):
            raise ValueError(
                f"Incident cannot transition from {current_status} to {transition.status}"
            )
        return self._repository.transition(incident_id, transition.status, transition.reason)
