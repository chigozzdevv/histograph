from typing import Any
from uuid import UUID, uuid4

from histograph.monitors.types import Monitor
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
