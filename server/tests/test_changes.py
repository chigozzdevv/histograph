from datetime import UTC, datetime

from histograph.changes.service import ChangeService, ReleaseContextService
from histograph.changes.types import Change


class FakeChanges:
    def __init__(self) -> None:
        self.saved: Change | None = None

    def save(self, change):
        self.saved = change
        return change.id

    def recent(self, start, end, environment="production"):
        saved = self.saved
        assert saved is not None
        return [
            {
                "id": saved.id,
                "asset_urn": saved.asset_urn,
                "asset_name": saved.asset_name,
                "asset_type": saved.asset_type,
                "version": saved.version,
                "environment": saved.environment,
                "change_type": saved.change_type,
                "status": saved.status,
                "occurred_at": saved.occurred_at,
                "metadata": saved.metadata,
            }
        ]


class FakeDeployments:
    def history(self, model, start, end, environment="production"):
        return []


def test_release_context_marks_only_changes_in_the_datahub_lineage() -> None:
    changes = FakeChanges()
    change = Change(
        asset_urn="urn:li:mlFeature:(mobile_money,account_velocity_24h)",
        asset_name="account_velocity_job",
        asset_type="feature",
        version="v2",
        change_type="configuration",
        status="applied",
        occurred_at=datetime(2026, 8, 8, 11, 0, tzinfo=UTC),
        metadata={"changed_features": ["account_velocity_24h"]},
    )
    ChangeService(changes).ingest(change)
    incident = {
        "model": "mobile-money-fraud",
        "evidence": {
            "detection": {
                "evaluation_window": {
                    "start": "2026-08-08T11:00:00Z",
                    "end": "2026-08-08T12:00:00Z",
                }
            }
        },
    }

    context = ReleaseContextService(changes, FakeDeployments()).collect(
        incident, [change.asset_urn]
    )

    assert context["changes"][0]["lineage_match"] is True
    assert context["changes"][0]["occurred_at"] == "2026-08-08T11:00:00+00:00"
    assert context["deployments"] == []
