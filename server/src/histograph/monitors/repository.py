from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.core.time import ensure_utc
from histograph.monitors.types import Monitor, MonitorEvent
from histograph.storage.postgres import PostgresDatabase


class MonitorRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def save(self, monitor: Monitor) -> UUID:
        monitor_id = uuid4()
        with self._database.connection() as connection:
            connection.execute(
                """
                INSERT INTO monitors (
                    id, model, version, environment, deployment, signal, metric, feature,
                    reference_version,
                    operator, threshold, baseline_window_minutes,
                    evaluation_window_minutes, minimum_sample_size, check_interval_seconds, enabled,
                    next_evaluation_at
                ) VALUES (
                    %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW()
                )
                """,
                (
                    monitor_id,
                    monitor.model,
                    monitor.version,
                    monitor.environment,
                    monitor.deployment,
                    monitor.signal,
                    monitor.metric,
                    monitor.feature,
                    monitor.reference_version,
                    monitor.operator,
                    monitor.threshold,
                    monitor.baseline_window_minutes,
                    monitor.evaluation_window_minutes,
                    monitor.minimum_sample_size,
                    monitor.check_interval_seconds,
                    monitor.enabled,
                ),
            )
            connection.commit()
        return monitor_id

    def get(self, monitor_id: UUID) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM monitors WHERE id = %s", (monitor_id,)
            ).fetchone()

    def list_all(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT monitors.*,
                           latest_run.status AS latest_run_status,
                           latest_run.result ->> 'status' AS latest_run_result_status,
                           latest_run.triggered AS latest_run_triggered,
                           latest_run.finished_at AS latest_run_at
                    FROM monitors
                    LEFT JOIN LATERAL (
                        SELECT status, result, triggered, finished_at
                        FROM monitor_runs
                        WHERE monitor_runs.monitor_id = monitors.id
                        ORDER BY started_at DESC
                        LIMIT 1
                    ) AS latest_run ON TRUE
                    ORDER BY monitors.created_at DESC, monitors.id
                    LIMIT %s
                    """,
                    (limit,),
                ).fetchall()
            )

    def runs(self, monitor_id: UUID, limit: int = 50) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM monitor_runs
                    WHERE monitor_id = %s
                    ORDER BY started_at DESC, id DESC
                    LIMIT %s
                    """,
                    (monitor_id, limit),
                ).fetchall()
            )

    def record_event(self, event: MonitorEvent, evidence: dict[str, Any]) -> UUID:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO monitor_events (
                    id, monitor_id, model, version, signal, metric,
                    observed_value, baseline_value, threshold, occurred_at,
                    affected_slice, evidence
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (monitor_id, occurred_at) DO UPDATE SET
                    observed_value = EXCLUDED.observed_value,
                    baseline_value = EXCLUDED.baseline_value,
                    threshold = EXCLUDED.threshold,
                    affected_slice = EXCLUDED.affected_slice,
                    evidence = EXCLUDED.evidence
                RETURNING id
                """,
                (
                    event.id,
                    event.monitor_id,
                    event.model,
                    event.version,
                    event.signal,
                    event.metric,
                    event.observed_value,
                    event.baseline_value,
                    event.threshold,
                    event.occurred_at,
                    Jsonb(event.affected_slice),
                    Jsonb(evidence),
                ),
            ).fetchone()
            connection.commit()
        if record is None:
            raise RuntimeError("Monitor event persistence did not return an identifier")
        return record["id"]

    def claim_due(
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
                        FROM monitors
                        WHERE enabled = TRUE
                          AND next_evaluation_at <= %s
                          AND (lease_expires_at IS NULL OR lease_expires_at <= %s)
                        ORDER BY next_evaluation_at, id
                        FOR UPDATE SKIP LOCKED
                        LIMIT %s
                    )
                    UPDATE monitors AS monitors
                    SET lease_owner = %s, lease_expires_at = %s, last_error = NULL
                    FROM candidates
                    WHERE monitors.id = candidates.id
                    RETURNING monitors.*
                    """,
                    (timestamp, timestamp, limit, worker_id, lease_until),
                ).fetchall()
            )
            for record in records:
                connection.execute(
                    """
                    INSERT INTO monitor_runs (
                        id, monitor_id, worker_id, scheduled_for, status
                    ) VALUES (%s, %s, %s, %s, 'running')
                    ON CONFLICT (monitor_id, scheduled_for) DO UPDATE SET
                        worker_id = EXCLUDED.worker_id,
                        started_at = NOW(),
                        finished_at = NULL,
                        status = 'running',
                        error = NULL
                    """,
                    (uuid4(), record["id"], worker_id, record["next_evaluation_at"]),
                )
            connection.commit()
            return records

    def complete_evaluation(
        self,
        monitor_id: UUID,
        scheduled_for: datetime,
        completed_at: datetime,
        result: dict[str, Any],
    ) -> None:
        timestamp = ensure_utc(completed_at)
        payload = json.loads(json.dumps(result, default=str))
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE monitors
                SET last_evaluated_at = %s,
                    next_evaluation_at = %s + make_interval(secs => check_interval_seconds),
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = NULL
                WHERE id = %s
                """,
                (timestamp, timestamp, monitor_id),
            )
            connection.execute(
                """
                UPDATE monitor_runs
                SET finished_at = %s,
                    status = 'evaluated',
                    triggered = %s,
                    result = %s
                WHERE monitor_id = %s AND scheduled_for = %s
                """,
                (
                    timestamp,
                    bool(result.get("triggered")),
                    Jsonb(payload),
                    monitor_id,
                    scheduled_for,
                ),
            )
            connection.commit()

    def fail_evaluation(
        self,
        monitor_id: UUID,
        scheduled_for: datetime,
        failed_at: datetime,
        error: str,
        retry_seconds: int,
    ) -> None:
        timestamp = ensure_utc(failed_at)
        retry_at = timestamp + timedelta(seconds=retry_seconds)
        with self._database.connection() as connection:
            connection.execute(
                """
                UPDATE monitors
                SET next_evaluation_at = %s,
                    lease_owner = NULL,
                    lease_expires_at = NULL,
                    last_error = %s
                WHERE id = %s
                """,
                (retry_at, error, monitor_id),
            )
            connection.execute(
                """
                UPDATE monitor_runs
                SET finished_at = %s, status = 'failed', error = %s
                WHERE monitor_id = %s AND scheduled_for = %s
                """,
                (timestamp, error, monitor_id, scheduled_for),
            )
            connection.commit()
