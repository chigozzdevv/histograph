from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.core.time import ensure_utc, utc_now
from histograph.storage.postgres import PostgresDatabase


class DemoRunRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def start(self, deployment: dict[str, Any], started_by: str) -> UUID:
        run_id = uuid4()
        baseline = {
            "baseline_revision": deployment["desired_revision"],
            "baseline_manifest": deployment["manifest_content"],
        }
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO demo_runs (
                    id, deployment_id, status, stage, started_by, result
                ) VALUES (%s, %s, 'queued', 'queued', %s, %s)
                ON CONFLICT DO NOTHING
                RETURNING id
                """,
                (run_id, deployment["id"], started_by, Jsonb(baseline)),
            ).fetchone()
            connection.commit()
        if record is None:
            raise ValueError("Another controlled demo scenario is already active")
        return run_id

    def get(self, run_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute("SELECT * FROM demo_runs WHERE id = %s", (run_id,)).fetchone()

    def list_all(self, limit: int = 20) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM demo_runs ORDER BY created_at DESC, id LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )

    def claim_queued(
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
                        SELECT id FROM demo_runs
                        WHERE status = 'queued'
                          AND (lease_expires_at IS NULL OR lease_expires_at <= %s)
                        ORDER BY created_at
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE demo_runs AS runs
                    SET status = 'running', stage = 'emitting_traffic',
                        lease_owner = %s, lease_expires_at = %s, updated_at = NOW(),
                        last_error = NULL
                    FROM candidates
                    WHERE runs.id = candidates.id
                    RETURNING runs.*
                    """,
                    (timestamp, limit, worker_id, lease_until),
                ).fetchall()
            )
            connection.commit()
            return records

    def mark_emitted(self, run_id: UUID, monitor_id: UUID, result: dict[str, Any]) -> None:
        with self._database.connection() as connection:
            current = connection.execute(
                "SELECT result FROM demo_runs WHERE id = %s FOR UPDATE", (run_id,)
            ).fetchone()
            existing = current.get("result") if current is not None else None
            combined = {**(existing if isinstance(existing, dict) else {}), "traffic": result}
            connection.execute(
                """
                UPDATE demo_runs
                SET monitor_id = %s, status = 'running', stage = 'monitoring', result = %s,
                    lease_owner = NULL, lease_expires_at = NULL, updated_at = NOW()
                WHERE id = %s
                """,
                (monitor_id, Jsonb(combined), run_id),
            )
            connection.commit()

    def fail(self, run_id: UUID, error: str) -> None:
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE demo_runs
                SET status = 'failed', stage = 'failed', last_error = %s,
                    lease_owner = NULL, lease_expires_at = NULL,
                    updated_at = NOW(), finished_at = NOW()
                WHERE id = %s
                """,
                (error, run_id),
            )
            connection.commit()

    def active(self) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM demo_runs
                    WHERE status IN ('running', 'awaiting_approval')
                    ORDER BY created_at
                    """
                ).fetchall()
            )

    def refresh(self, run_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            run = connection.execute(
                "SELECT * FROM demo_runs WHERE id = %s FOR UPDATE", (run_id,)
            ).fetchone()
            if run is None or run["status"] in {"queued", "failed", "resolved"}:
                return run
            monitor_id = run.get("monitor_id")
            incident = None
            if monitor_id is not None:
                incident = connection.execute(
                    """
                    SELECT * FROM incidents
                    WHERE monitor_id = %s
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (monitor_id,),
                ).fetchone()
            action = None
            if incident is not None:
                action = connection.execute(
                    """
                    SELECT * FROM remediation_actions
                    WHERE incident_id = %s
                    ORDER BY proposed_at DESC LIMIT 1
                    """,
                    (incident["id"],),
                ).fetchone()
            status, stage, finished_at = _state(run, incident, action)
            connection.execute(
                """
                UPDATE demo_runs
                SET status = %s, stage = %s, incident_id = %s, action_id = %s,
                    updated_at = NOW(), finished_at = %s
                WHERE id = %s
                """,
                (
                    status,
                    stage,
                    incident["id"] if incident is not None else None,
                    action["id"] if action is not None else None,
                    finished_at,
                    run_id,
                ),
            )
            connection.commit()
        return self.get(run_id)

    def record_reset(self, run_id: UUID, reset: dict[str, Any]) -> None:
        with self._database.connection() as connection:
            current = connection.execute(
                "SELECT result FROM demo_runs WHERE id = %s FOR UPDATE", (run_id,)
            ).fetchone()
            if current is None:
                raise LookupError("Demo scenario not found")
            result = current.get("result")
            combined = {**(result if isinstance(result, dict) else {}), "reset": reset}
            connection.execute(
                "UPDATE demo_runs SET result = %s, updated_at = NOW() WHERE id = %s",
                (Jsonb(combined), run_id),
            )
            connection.commit()


def _state(
    run: dict[str, Any],
    incident: dict[str, Any] | None,
    action: dict[str, Any] | None,
) -> tuple[str, str, datetime | None]:
    if incident is None:
        return "running", "monitoring", None
    if incident["status"] == "resolved":
        return "resolved", "resolved", utc_now()
    if action is None:
        return "running", "investigating", None
    if action["status"] == "proposed":
        return "awaiting_approval", "awaiting_approval", None
    if action["status"] in {"approved", "executing"}:
        return "running", "remediating", None
    if action["status"] == "succeeded":
        return "running", "verifying", None
    if action["status"] in {"failed", "rejected", "cancelled"}:
        return "failed", "failed", utc_now()
    return run["status"], run["stage"], run.get("finished_at")
