from datetime import datetime
from typing import Any
from uuid import UUID

from psycopg.types.json import Jsonb

from histograph.changes.types import Change
from histograph.storage.postgres import PostgresDatabase


class ChangeRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def save(self, change: Change) -> UUID:
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO changes (
                    id, asset_urn, asset_name, asset_type, version, environment,
                    change_type, status, occurred_at, metadata
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (id) DO UPDATE SET
                    status = EXCLUDED.status,
                    occurred_at = EXCLUDED.occurred_at,
                    metadata = EXCLUDED.metadata
                RETURNING id
                """,
                (
                    change.id,
                    change.asset_urn,
                    change.asset_name,
                    change.asset_type,
                    change.version,
                    change.environment,
                    change.change_type,
                    change.status,
                    change.occurred_at,
                    Jsonb(change.metadata),
                ),
            ).fetchone()
            connection.commit()
        if record is None:
            raise RuntimeError("Change persistence did not return an identifier")
        return record["id"]

    def recent(
        self,
        start: datetime,
        end: datetime,
        environment: str = "production",
    ) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM changes
                    WHERE environment = %s
                      AND occurred_at >= %s
                      AND occurred_at <= %s
                    ORDER BY occurred_at DESC, created_at DESC
                    """,
                    (environment, start, end),
                ).fetchall()
            )

    def latest(self, asset_urn: str, environment: str = "production") -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                """
                SELECT * FROM changes
                WHERE asset_urn = %s AND environment = %s
                ORDER BY occurred_at DESC, created_at DESC
                LIMIT 1
                """,
                (asset_urn, environment),
            ).fetchone()
