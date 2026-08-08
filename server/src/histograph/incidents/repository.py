from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.core.time import utc_now
from histograph.monitors.types import MonitorEvent
from histograph.storage.postgres import PostgresDatabase


class IncidentRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def create(self, event: MonitorEvent, summary: str, evidence: dict[str, Any]) -> UUID:
        incident_id = uuid4()
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO incidents (
                    id, monitor_event_id, model, version, signal, metric,
                    status, severity, summary, evidence, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)
                """,
                (
                    incident_id,
                    event.monitor_id,
                    event.model,
                    event.version,
                    event.signal,
                    event.metric,
                    "high" if event.signal in {"performance", "feature_drift"} else "medium",
                    summary,
                    Jsonb(evidence),
                    utc_now(),
                ),
            )
            connection.commit()
        return incident_id

    def get(self, incident_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM incidents WHERE id = %s", (incident_id,)
            ).fetchone()

    def update(self, incident_id: UUID, summary: str, evidence: dict[str, Any]) -> bool:
        with self._database.connection() as connection:
            result = connection.execute(
                """
                UPDATE incidents
                SET summary = %s, evidence = %s
                WHERE id = %s
                """,
                (summary, Jsonb(evidence), incident_id),
            )
            connection.commit()
            return result.rowcount == 1

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT %s", (limit,)
                ).fetchall()
            )
