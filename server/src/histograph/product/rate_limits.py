from datetime import timedelta

from histograph.core.time import utc_now
from histograph.storage.postgres import PostgresDatabase


class RateLimitRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def consume(
        self,
        bucket: str,
        client_key: str,
        *,
        limit: int,
        window_seconds: int,
    ) -> bool:
        now = utc_now()
        reset_before = now - timedelta(seconds=window_seconds)
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO api_rate_limits (
                    bucket, client_key, window_started_at, request_count
                ) VALUES (%s, %s, %s, 1)
                ON CONFLICT (bucket, client_key) DO UPDATE SET
                    window_started_at = CASE
                        WHEN api_rate_limits.window_started_at <= %s
                        THEN EXCLUDED.window_started_at
                        ELSE api_rate_limits.window_started_at
                    END,
                    request_count = CASE
                        WHEN api_rate_limits.window_started_at <= %s THEN 1
                        ELSE api_rate_limits.request_count + 1
                    END
                RETURNING request_count
                """,
                (bucket, client_key, now, reset_before, reset_before),
            ).fetchone()
            connection.commit()
        return record is not None and int(record["request_count"]) <= limit
