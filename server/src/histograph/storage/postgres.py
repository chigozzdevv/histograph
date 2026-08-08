from collections.abc import Generator
from contextlib import contextmanager
from hashlib import sha256
from pathlib import Path
from typing import Any, LiteralString, cast

from psycopg import Connection, connect, sql
from psycopg.rows import dict_row


class PostgresDatabase:
    def __init__(self, dsn: str, migrations_path: Path | None = None):
        self._dsn = dsn
        self._migrations_path = migrations_path or (
            Path(__file__).resolve().parents[3] / "migrations" / "postgres"
        )

    @contextmanager
    def connection(self) -> Generator[Connection[dict[str, Any]]]:
        with connect(self._dsn, row_factory=dict_row) as connection:
            yield cast(Connection[dict[str, Any]], connection)

    def migrate(self) -> None:
        migrations = sorted(self._migrations_path.glob("*.sql"))
        if not migrations:
            raise RuntimeError(f"No Postgres migrations found in {self._migrations_path}")

        with self.connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS histograph_schema_migrations (
                    version TEXT PRIMARY KEY,
                    checksum TEXT NOT NULL,
                    applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """
            )
            for migration in migrations:
                version = migration.stem
                statement = migration.read_text()
                checksum = sha256(statement.encode()).hexdigest()
                current = connection.execute(
                    """
                    SELECT checksum FROM histograph_schema_migrations
                    WHERE version = %s
                    """,
                    (version,),
                ).fetchone()
                if current is not None:
                    if current["checksum"] != checksum:
                        raise RuntimeError(
                            f"Postgres migration {version} changed after it was applied"
                        )
                    continue

                connection.execute(sql.SQL(cast(LiteralString, statement)))
                connection.execute(
                    """
                    INSERT INTO histograph_schema_migrations (version, checksum)
                    VALUES (%s, %s)
                    """,
                    (version, checksum),
                )
            connection.commit()

    def ping(self) -> None:
        with self.connection() as connection:
            connection.execute("SELECT 1").fetchone()
