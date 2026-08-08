from typing import Any
from uuid import UUID, uuid4

import pytest
from pydantic import ValidationError

from histograph.incidents.service import IncidentService
from histograph.incidents.types import IncidentTransition


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


def test_resolving_an_incident_requires_a_reason() -> None:
    with pytest.raises(ValidationError):
        IncidentTransition(status="resolved")


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
