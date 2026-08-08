from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast
from uuid import UUID, uuid4

from psycopg import Connection, connect
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from histograph.contracts.events import Deployment, Monitor, MonitorEvent
from histograph.core.time import utc_now

SCHEMA = """
CREATE TABLE IF NOT EXISTS deployments (
    id UUID PRIMARY KEY,
    deployment TEXT NOT NULL,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    environment TEXT NOT NULL,
    strategy TEXT NOT NULL,
    traffic_percentage DOUBLE PRECISION NOT NULL,
    status TEXT NOT NULL,
    endpoint TEXT,
    occurred_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS deployments_model_version_idx
    ON deployments (model, version, occurred_at DESC);

CREATE TABLE IF NOT EXISTS monitors (
    id UUID PRIMARY KEY,
    model TEXT NOT NULL,
    version TEXT,
    signal TEXT NOT NULL,
    metric TEXT NOT NULL,
    operator TEXT NOT NULL,
    threshold DOUBLE PRECISION NOT NULL,
    baseline_window_minutes INTEGER NOT NULL,
    evaluation_window_minutes INTEGER NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS monitors_model_idx ON monitors (model, enabled);

CREATE TABLE IF NOT EXISTS incidents (
    id UUID PRIMARY KEY,
    monitor_event_id UUID,
    model TEXT NOT NULL,
    version TEXT NOT NULL,
    signal TEXT NOT NULL,
    metric TEXT NOT NULL,
    status TEXT NOT NULL,
    severity TEXT NOT NULL,
    summary TEXT NOT NULL,
    evidence JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS incidents_model_idx ON incidents (model, created_at DESC);
"""


class PostgresStore:
    def __init__(self, dsn: str):
        self._dsn = dsn

    @contextmanager
    def connection(self) -> Generator[Connection[dict[str, Any]]]:
        with connect(self._dsn, row_factory=dict_row) as connection:
            yield cast(Connection[dict[str, Any]], connection)

    def initialize(self) -> None:
        with self.connection() as connection:
            connection.execute(SCHEMA)
            connection.commit()

    def save_deployment(self, deployment: Deployment) -> UUID:
        deployment_id = uuid4()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO deployments (
                    id, deployment, model, version, environment, strategy,
                    traffic_percentage, status, endpoint, occurred_at
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    deployment_id,
                    deployment.deployment,
                    deployment.model,
                    deployment.version,
                    deployment.environment,
                    deployment.strategy,
                    deployment.traffic_percentage,
                    deployment.status,
                    deployment.endpoint,
                    deployment.occurred_at,
                ),
            )
            connection.commit()
        return deployment_id

    def save_monitor(self, monitor: Monitor) -> UUID:
        monitor_id = uuid4()
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO monitors (
                    id, model, version, signal, metric, operator, threshold,
                    baseline_window_minutes, evaluation_window_minutes, enabled
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    monitor_id,
                    monitor.model,
                    monitor.version,
                    monitor.signal,
                    monitor.metric,
                    monitor.operator,
                    monitor.threshold,
                    monitor.baseline_window_minutes,
                    monitor.evaluation_window_minutes,
                    monitor.enabled,
                ),
            )
            connection.commit()
        return monitor_id

    def get_monitor(self, monitor_id: UUID) -> dict[str, Any] | None:
        with self.connection() as connection:
            return connection.execute(
                "SELECT * FROM monitors WHERE id = %s", (monitor_id,)
            ).fetchone()

    def create_incident(self, event: MonitorEvent, summary: str, evidence: dict[str, Any]) -> UUID:
        incident_id = uuid4()
        with self.connection() as connection:
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

    def get_incident(self, incident_id: UUID) -> dict[str, Any] | None:
        with self.connection() as connection:
            return connection.execute(
                "SELECT * FROM incidents WHERE id = %s", (incident_id,)
            ).fetchone()

    def update_incident(
        self, incident_id: UUID, summary: str, evidence: dict[str, Any]
    ) -> bool:
        with self.connection() as connection:
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

    def list_incidents(self, limit: int = 50) -> list[dict[str, Any]]:
        with self.connection() as connection:
            return list(
                connection.execute(
                    "SELECT * FROM incidents ORDER BY created_at DESC LIMIT %s", (limit,)
                ).fetchall()
            )
