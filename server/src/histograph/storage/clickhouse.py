from hashlib import sha256
from pathlib import Path
from re import fullmatch

import clickhouse_connect
from clickhouse_connect.driver.client import Client


class ClickHouseDatabase:
    def __init__(
        self,
        host: str,
        port: int,
        database: str,
        user: str,
        password: str,
        migrations_path: Path | None = None,
    ):
        if fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database) is None:
            raise ValueError("ClickHouse database name must be a valid identifier")
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
        self._migrations_path = migrations_path or (
            Path(__file__).resolve().parents[3] / "migrations" / "clickhouse"
        )
        self._client: Client | None = None

    @property
    def name(self) -> str:
        return self._database

    @property
    def client(self) -> Client:
        if self._client is None:
            self._client = clickhouse_connect.get_client(
                host=self._host,
                port=self._port,
                username=self._user,
                password=self._password,
            )
        return self._client

    def migrate(self) -> None:
        migrations = sorted(self._migrations_path.glob("*.sql"))
        if not migrations:
            raise RuntimeError(f"No ClickHouse migrations found in {self._migrations_path}")

        self.client.command(f"CREATE DATABASE IF NOT EXISTS {self._database}")
        self.client.command(
            f"""
            CREATE TABLE IF NOT EXISTS {self._database}.histograph_schema_migrations (
                version String,
                checksum String,
                applied_at DateTime64(3, 'UTC') DEFAULT now64(3)
            ) ENGINE = MergeTree
            ORDER BY version
            """
        )
        for migration in migrations:
            version = migration.stem
            statement = migration.read_text()
            checksum = sha256(statement.encode()).hexdigest()
            result = self.client.query(
                f"""
                SELECT checksum
                FROM {self._database}.histograph_schema_migrations
                WHERE version = %(version)s
                ORDER BY applied_at DESC
                LIMIT 1
                """,
                parameters={"version": version},
            )
            if result.result_rows:
                if result.result_rows[0][0] != checksum:
                    raise RuntimeError(
                        f"ClickHouse migration {version} changed after it was applied"
                    )
                continue

            self.client.command(statement.format(database=self._database))
            self.client.insert(
                f"{self._database}.histograph_schema_migrations",
                [[version, checksum]],
                column_names=["version", "checksum"],
            )

    def ping(self) -> None:
        self.client.command("SELECT 1")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
