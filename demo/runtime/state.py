import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from histograph.core.time import ensure_utc


class RuntimeStateStore:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self._path = path
        self._migrate()

    def apply_manifest(
        self,
        deployment: str,
        revision: str,
        content: str,
        applied_at: datetime,
        events: list[tuple[str, dict[str, Any]]],
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO runtime_deployments (deployment, revision, manifest_content, applied_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(deployment) DO UPDATE SET
                    revision = excluded.revision,
                    manifest_content = excluded.manifest_content,
                    applied_at = excluded.applied_at
                """,
                (deployment, revision, content, _timestamp(applied_at)),
            )
            for event_type, payload in events:
                self._enqueue(connection, event_type, payload, applied_at)

    def latest_manifest(self) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT deployment, revision, manifest_content, applied_at
                FROM runtime_deployments
                ORDER BY applied_at DESC
                LIMIT 1
                """
            ).fetchone()
        return dict(row) if row is not None else None

    def enqueue(self, event_type: str, payload: dict[str, Any], created_at: datetime) -> None:
        with self._connection() as connection:
            self._enqueue(connection, event_type, payload, created_at)

    def due(self, now: datetime, limit: int) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, payload, attempt_count
                FROM telemetry_outbox
                WHERE next_attempt_at <= ?
                ORDER BY id
                LIMIT ?
                """,
                (_timestamp(now), limit),
            ).fetchall()
        return [{**dict(row), "payload": json.loads(row["payload"])} for row in rows]

    def complete(self, event_id: int) -> None:
        with self._connection() as connection:
            connection.execute("DELETE FROM telemetry_outbox WHERE id = ?", (event_id,))

    def fail(self, event_id: int, error: str, now: datetime, retry_seconds: int) -> None:
        retry_at = ensure_utc(now) + timedelta(seconds=retry_seconds)
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE telemetry_outbox
                SET attempt_count = attempt_count + 1,
                    next_attempt_at = ?,
                    last_error = ?
                WHERE id = ?
                """,
                (_timestamp(retry_at), error[:2000], event_id),
            )

    def pending_count(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS count FROM telemetry_outbox").fetchone()
        return int(row["count"]) if row is not None else 0

    def reconciler_deployment(self, deployment: str) -> dict[str, Any] | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT deployment, revision, github_deployment_id, status, last_error, updated_at
                FROM reconciler_deployments
                WHERE deployment = ?
                """,
                (deployment,),
            ).fetchone()
        return dict(row) if row is not None else None

    def save_reconciler_deployment(
        self,
        deployment: str,
        revision: str,
        github_deployment_id: int,
        status: str,
        updated_at: datetime,
        error: str | None = None,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO reconciler_deployments (
                    deployment, revision, github_deployment_id, status, last_error, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(deployment) DO UPDATE SET
                    revision = excluded.revision,
                    github_deployment_id = excluded.github_deployment_id,
                    status = excluded.status,
                    last_error = excluded.last_error,
                    updated_at = excluded.updated_at
                """,
                (
                    deployment,
                    revision,
                    github_deployment_id,
                    status,
                    error,
                    _timestamp(updated_at),
                ),
            )

    def close(self) -> None:
        return None

    def _migrate(self) -> None:
        with self._connection() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS runtime_deployments (
                    deployment TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    manifest_content TEXT NOT NULL,
                    applied_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS telemetry_outbox (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    event_type TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    attempt_count INTEGER NOT NULL DEFAULT 0,
                    next_attempt_at TEXT NOT NULL,
                    last_error TEXT,
                    created_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS telemetry_outbox_due_idx
                    ON telemetry_outbox (next_attempt_at, id);
                CREATE TABLE IF NOT EXISTS reconciler_deployments (
                    deployment TEXT PRIMARY KEY,
                    revision TEXT NOT NULL,
                    github_deployment_id INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    last_error TEXT,
                    updated_at TEXT NOT NULL
                );
                """
            )

    def _connection(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self._path, timeout=30)
        connection.row_factory = sqlite3.Row
        return connection

    @staticmethod
    def _enqueue(
        connection: sqlite3.Connection,
        event_type: str,
        payload: dict[str, Any],
        created_at: datetime,
    ) -> None:
        connection.execute(
            """
            INSERT INTO telemetry_outbox (
                event_type, payload, next_attempt_at, created_at
            ) VALUES (?, ?, ?, ?)
            """,
            (
                event_type,
                json.dumps(payload, separators=(",", ":"), sort_keys=True),
                _timestamp(created_at),
                _timestamp(created_at),
            ),
        )


def _timestamp(value: datetime) -> str:
    return ensure_utc(value).isoformat()
