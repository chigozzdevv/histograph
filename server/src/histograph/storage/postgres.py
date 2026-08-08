from collections.abc import Generator
from contextlib import contextmanager
from typing import Any, cast

from psycopg import Connection, connect
from psycopg.rows import dict_row

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


class PostgresDatabase:
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

    def ping(self) -> None:
        with self.connection() as connection:
            connection.execute("SELECT 1").fetchone()
