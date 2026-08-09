from datetime import datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from histograph.changes.types import Change
from histograph.core.time import ensure_utc, utc_now


class ChangeWriter(Protocol):
    def save(self, change: Change) -> UUID: ...


class ChangeService:
    def __init__(self, repository: ChangeWriter):
        self._repository = repository

    def ingest(self, change: Change) -> UUID:
        return self._repository.save(change)


class ChangeReader(Protocol):
    def recent(
        self, start: datetime, end: datetime, environment: str = "production"
    ) -> list[dict[str, Any]]: ...


class DeploymentReader(Protocol):
    def history(
        self,
        model: str,
        start: datetime,
        end: datetime,
        environment: str = "production",
    ) -> list[dict[str, Any]]: ...


class ReleaseContextService:
    def __init__(self, changes: ChangeReader, deployments: DeploymentReader):
        self._changes = changes
        self._deployments = deployments

    def collect(self, incident: dict[str, Any], asset_urns: list[str]) -> dict[str, Any]:
        start, end = _release_window(incident)
        environment = _incident_environment(incident)
        model = incident.get("model")
        deployments = (
            self._deployments.history(model, start, end, environment)
            if isinstance(model, str)
            else []
        )
        assets = set(asset_urns)
        changes = [
            {**_jsonable(change), "lineage_match": change.get("asset_urn") in assets}
            for change in self._changes.recent(start, end, environment)
        ]
        return {
            "window": {"start": start.isoformat(), "end": end.isoformat()},
            "changes": changes,
            "deployments": [_jsonable(deployment) for deployment in deployments],
        }


def _release_window(incident: dict[str, Any]) -> tuple[datetime, datetime]:
    evidence = incident.get("evidence")
    detection = evidence.get("detection") if isinstance(evidence, dict) else None
    if isinstance(detection, dict):
        window = detection.get("evaluation_window") or detection.get("window")
        if isinstance(window, dict):
            start = _parse_timestamp(window.get("start"))
            end = _parse_timestamp(window.get("end"))
            if start is not None and end is not None:
                recovery = evidence.get("recovery") if isinstance(evidence, dict) else None
                verified_at = (
                    _parse_timestamp(recovery.get("verified_at"))
                    if isinstance(recovery, dict)
                    else None
                )
                return start - timedelta(minutes=30), max(end, verified_at or end)
    created_at = incident.get("created_at")
    end = ensure_utc(created_at) if isinstance(created_at, datetime) else utc_now()
    return end - timedelta(minutes=60), end


def _parse_timestamp(value: object) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return ensure_utc(datetime.fromisoformat(value.replace("Z", "+00:00")))
    except ValueError:
        return None


def _incident_environment(incident: dict[str, Any]) -> str:
    evidence = incident.get("evidence")
    trigger = evidence.get("trigger") if isinstance(evidence, dict) else None
    affected_slice = trigger.get("affected_slice") if isinstance(trigger, dict) else None
    environment = affected_slice.get("environment") if isinstance(affected_slice, dict) else None
    return environment if isinstance(environment, str) else "production"


def _jsonable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value
