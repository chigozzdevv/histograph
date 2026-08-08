from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

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
                    id, model, version, environment, deployment, signal, metric,
                    operator, threshold, baseline_window_minutes,
                    evaluation_window_minutes, minimum_sample_size, enabled
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    monitor_id,
                    monitor.model,
                    monitor.version,
                    monitor.environment,
                    monitor.deployment,
                    monitor.signal,
                    monitor.metric,
                    monitor.operator,
                    monitor.threshold,
                    monitor.baseline_window_minutes,
                    monitor.evaluation_window_minutes,
                    monitor.minimum_sample_size,
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
