from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.core.time import ensure_utc, utc_now
from histograph.incidents.types import RecoveryVerification
from histograph.monitors.types import MonitorEvent
from histograph.storage.postgres import PostgresDatabase


class IncidentRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def create(self, event: MonitorEvent, summary: str, evidence: dict[str, Any]) -> UUID:
        incident_id = uuid4()
        with self._database.connection() as connection:
            existing = connection.execute(
                "SELECT id FROM incidents WHERE monitor_event_id = %s", (event.id,)
            ).fetchone()
            if existing is not None:
                return existing["id"]
            record = connection.execute(
                """
                INSERT INTO incidents (
                    id, monitor_id, monitor_event_id, model, version, signal, metric,
                    status, severity, summary, evidence, created_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, 'open', %s, %s, %s, %s)
                ON CONFLICT (monitor_id)
                    WHERE monitor_id IS NOT NULL AND status IN ('open', 'investigating')
                DO UPDATE SET monitor_id = EXCLUDED.monitor_id
                RETURNING id
                """,
                (
                    incident_id,
                    event.monitor_id,
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
            else:
                connection.execute(
                    """
                    INSERT INTO incident_events (id, incident_id, event_type, details)
                    VALUES (%s, %s, 'signal_repeated', %s)
                    """,
                    (
                        uuid4(),
                        persisted_id,
                        Jsonb(
                            {
                                "monitor_event_id": str(event.id),
                                "observed_value": event.observed_value,
                                "occurred_at": event.occurred_at.isoformat(),
                            }
                        ),
                    ),
                )
            connection.commit()
        return persisted_id

    def get(self, incident_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM incidents WHERE id = %s", (incident_id,)
            ).fetchone()

    def get_with_monitor(self, incident_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                """
                SELECT incidents.*
                FROM incidents
                WHERE incidents.id = %s
                """,
                (incident_id,),
            ).fetchone()

    def claim_investigations(
        self,
        worker_id: str,
        now: datetime,
        limit: int,
        lease_seconds: int,
    ) -> list[dict[str, Any]]:
        timestamp = ensure_utc(now)
        lease_until = timestamp + timedelta(seconds=lease_seconds)
        with self._database.connection() as connection:
            records = list(
                connection.execute(
                    """
                    WITH candidates AS (
                        SELECT id
                        FROM incidents
                        WHERE status IN ('open', 'investigating')
                          AND investigation_status IN ('pending', 'failed')
                          AND investigation_next_attempt_at <= %s
                          AND (
                              investigation_lease_expires_at IS NULL
                              OR investigation_lease_expires_at <= %s
                          )
                        ORDER BY investigation_next_attempt_at, created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE incidents AS incidents
                    SET investigation_status = 'running',
                        investigation_attempts = investigation_attempts + 1,
                        investigation_lease_owner = %s,
                        investigation_lease_expires_at = %s,
                        investigation_last_error = NULL
                    FROM candidates
                    WHERE incidents.id = candidates.id
                    RETURNING incidents.*
                    """,
                    (timestamp, timestamp, limit, worker_id, lease_until),
                ).fetchall()
            )
            connection.commit()
            return records

    def complete_investigation(self, incident_id: UUID) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE incidents
                SET investigation_status = 'completed',
                    investigation_lease_owner = NULL,
                    investigation_lease_expires_at = NULL,
                    investigation_last_error = NULL
                WHERE id = %s
                """,
                (incident_id,),
            )
            connection.commit()

    def fail_investigation(
        self, incident_id: UUID, failed_at: datetime, error: str, retry_seconds: int
    ) -> None:
        retry_at = ensure_utc(failed_at) + timedelta(seconds=retry_seconds)
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE incidents
                SET investigation_status = 'failed',
                    investigation_next_attempt_at = %s,
                    investigation_lease_owner = NULL,
                    investigation_lease_expires_at = NULL,
                    investigation_last_error = %s
                WHERE id = %s
                """,
                (retry_at, error, incident_id),
            )
            connection.commit()

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
                    Jsonb(
                        {
                            "from": current["status"],
                            "to": status,
                            "reason": reason,
                            "recovery_verified": status == "resolved",
                        }
                    ),
                ),
            )
            connection.commit()
            return updated

    def record_recovery(
        self,
        incident_id: UUID,
        recovery: RecoveryVerification,
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            current = connection.execute(
                "SELECT * FROM incidents WHERE id = %s FOR UPDATE", (incident_id,)
            ).fetchone()
            if current is None:
                return None
            evidence = current.get("evidence")
            existing_recovery = evidence.get("recovery") if isinstance(evidence, dict) else None
            recovery_payload = recovery.model_dump(mode="json")
            if existing_recovery == recovery_payload:
                return current
            updated_evidence = {
                **(evidence if isinstance(evidence, dict) else {}),
                "recovery": recovery_payload,
            }
            connection.execute(
                "UPDATE incidents SET evidence = %s WHERE id = %s",
                (Jsonb(updated_evidence), incident_id),
            )
            connection.execute(
                """
                INSERT INTO incident_events (id, incident_id, event_type, details)
                VALUES (%s, %s, 'recovery_verified', %s)
                """,
                (uuid4(), incident_id, Jsonb(recovery_payload)),
            )
            connection.commit()
            return {**current, "evidence": updated_evidence}

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
