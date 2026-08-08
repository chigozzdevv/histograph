from typing import Any
from uuid import UUID

from histograph.monitors.types import MonitorEvent
from histograph.storage.postgres import PostgresStore


class IncidentService:
    def __init__(self, control: PostgresStore):
        self._control = control

    def create_from_monitor_event(
        self, event: MonitorEvent, detection_evidence: dict[str, Any]
    ) -> UUID:
        observed = event.observed_value
        baseline = (
            "unavailable" if event.baseline_value is None else f"{event.baseline_value:.6f}"
        )
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
        return self._control.create_incident(event, summary, evidence)
