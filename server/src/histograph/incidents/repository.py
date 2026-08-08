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
            record = connection.execute(
                """
                INSERT INTO incidents (
                    id, monitor_event_id, model, version, signal, metric,
                    status, severity, summary, evidence, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)
                ON CONFLICT (monitor_event_id) WHERE monitor_event_id IS NOT NULL
                DO UPDATE SET monitor_event_id = EXCLUDED.monitor_event_id
                RETURNING id
                """,
                (
                    incident_id,
                    event.id,
                    event.model,
                    event.version,
                    event.signal,
                    event.metric,
                    "high" if event.signal in {"performance", "feature_drift"} else "medium",
                    summary,
                    Jsonb(evidence),
                    utc_now(),
                ),
            ).fetchone()
            if record is None:
                raise RuntimeError("Incident persistence did not return an identifier")
            persisted_id = record["id"]
            if persisted_id == incident_id:
                connection.execute(
                    """
                    INSERT INTO incident_events (id, incident_id, event_type, details)
                    VALUES (%s, %s, 'created', %s)
                    """,
                    (uuid4(), incident_id, Jsonb({"monitor_event_id": str(event.id)})),
                )
            connection.commit()
        return persisted_id

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
            if result.rowcount == 1:
                connection.execute(
                    """
                    INSERT INTO incident_events (id, incident_id, event_type, details)
                    VALUES (%s, %s, 'investigation_updated', %s)
                    """,
                    (uuid4(), incident_id, Jsonb({"summary": summary, "evidence": evidence})),
                )
            connection.commit()
            return result.rowcount == 1

    def transition(
        self,
        incident_id: UUID,
        status: str,
        reason: str | None,
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            current = connection.execute(
                "SELECT * FROM incidents WHERE id = %s FOR UPDATE", (incident_id,)
            ).fetchone()
            if current is None:
                return None
            resolved_at = utc_now() if status in {"resolved", "closed"} else None
            connection.execute(
                """
                UPDATE incidents
                SET status = %s, resolved_at = %s
                WHERE id = %s
                """,
                (status, resolved_at, incident_id),
            )
            updated = {
                **current,
                "status": status,
                "resolved_at": resolved_at,
            }
            connection.execute(
                """
                INSERT INTO incident_events (id, incident_id, event_type, details)
                VALUES (%s, %s, 'status_changed', %s)
                """,
                (
                    uuid4(),
                    incident_id,
                    Jsonb({"from": current["status"], "to": status, "reason": reason}),
                ),
            )
            connection.commit()
            return updated

    def events(self, incident_id: UUID) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM incident_events
                    WHERE incident_id = %s
                    ORDER BY created_at, id
                    """,
                    (incident_id,),
                ).fetchall()
            )

    def list(self, limit: int = 50) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT %s", (limit,)
                ).fetchall()
            )
