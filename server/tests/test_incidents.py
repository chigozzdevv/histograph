from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from histograph.incidents.service import IncidentService
from histograph.incidents.types import IncidentTransition, RecoveryVerification


class FakeIncidentStore:
    def __init__(self, status: str = "open") -> None:
        self.incident_id = uuid4()
        self.record: dict[str, Any] = {"id": self.incident_id, "status": status}
        self.transitioned: tuple[UUID, str, str | None] | None = None

    def create(self, event, summary, evidence):
        return self.incident_id

    def get(self, incident_id):
        return self.record if incident_id == self.incident_id else None

    def transition(self, incident_id, status, reason):
        self.transitioned = (incident_id, status, reason)
        self.record = {**self.record, "status": status}
        return self.record

    def record_recovery(self, incident_id, recovery):
        self.record = {
            **self.record,
            "evidence": {"recovery": recovery.model_dump(mode="json")},
        }
        return self.record


def test_manually_closing_an_incident_requires_a_reason() -> None:
    with pytest.raises(ValidationError):
        IncidentTransition(status="closed")


def test_resolving_an_incident_requires_verified_recovery() -> None:
    store = FakeIncidentStore()

    with pytest.raises(ValueError, match="until recovery has been verified"):
        IncidentService(store).transition(
            store.incident_id,
            IncidentTransition(status="resolved"),
        )


def test_resolving_an_incident_accepts_persisted_verified_recovery() -> None:
    store = FakeIncidentStore()
    store.record["evidence"] = {
        "recovery": {
            "status": "verified",
            "verified_at": "2026-08-08T12:00:00Z",
            "checks": [
                {
                    "name": "performance_recovered",
                    "passed": True,
                    "details": {"accuracy": 0.98},
                }
            ],
        }
    }

    result = IncidentService(store).transition(
        store.incident_id,
        IncidentTransition(status="resolved"),
    )

    assert result is not None
    assert result["status"] == "resolved"
    assert store.transitioned == (store.incident_id, "resolved", None)


def test_incident_service_enforces_status_transitions() -> None:
    store = FakeIncidentStore(status="resolved")
    service = IncidentService(store)

    with pytest.raises(ValueError, match="resolved to investigating"):
        service.transition(
            store.incident_id,
            IncidentTransition(status="investigating"),
        )


def test_incident_service_records_valid_transition() -> None:
    store = FakeIncidentStore()

    result = IncidentService(store).transition(
        store.incident_id,
        IncidentTransition(status="investigating"),
    )

    assert result is not None
    assert result["status"] == "investigating"
    assert store.transitioned == (store.incident_id, "investigating", None)


def test_recording_recovery_persists_structured_verification() -> None:
    store = FakeIncidentStore()
    recovery = RecoveryVerification.model_validate(
        {
            "status": "verified",
            "verified_at": "2026-08-08T12:00:00Z",
            "checks": [
                {
                    "name": "recall_recovered",
                    "passed": True,
                    "details": {
                        "baseline": 0.82,
                        "observed": 0.81,
                        "relative_change_percent": -1.22,
                    },
                }
            ],
        }
    )

    result = IncidentService(store).record_recovery(store.incident_id, recovery)

    assert result is not None
    assert result["evidence"]["recovery"]["status"] == "verified"
