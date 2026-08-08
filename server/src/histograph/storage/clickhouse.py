import clickhouse_connect
from clickhouse_connect.driver.client import Client


class ClickHouseDatabase:
    def __init__(self, host: str, port: int, database: str, user: str, password: str):
        self._host = host
        self._port = port
        self._database = database
        self._user = user
        self._password = password
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

    def initialize(self) -> None:
        self.client.command(f"CREATE DATABASE IF NOT EXISTS {self._database}")

    def ping(self) -> None:
        self.client.command("SELECT 1")

    def close(self) -> None:
        if self._client is not None:
            self._client.close()
            self._client = None
