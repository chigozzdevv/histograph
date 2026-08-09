from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from histograph.deployments.types import Deployment
from histograph.storage.postgres import PostgresDatabase


class DeploymentRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def save(self, deployment: Deployment) -> UUID:
        deployment_id = uuid4()
        with self._database.connection() as connection:
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

    def active_versions(
        self,
        model: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    WITH latest AS (
                        SELECT DISTINCT ON (deployment, version)
                            deployment, version, strategy, traffic_percentage,
                            status, endpoint, occurred_at
                        FROM deployments
                        WHERE model = %s
                          AND environment = %s
                          AND (%s::text IS NULL OR deployment = %s::text)
                        ORDER BY deployment, version, occurred_at DESC, created_at DESC
                    )
                    SELECT *
                    FROM latest
                    WHERE status IN ('monitoring', 'active')
                      AND traffic_percentage > 0
                    ORDER BY occurred_at DESC, version
                    """,
                    (model, environment, deployment, deployment),
                ).fetchall()
            )

    def history(
        self,
        model: str,
        start: datetime,
        end: datetime,
        environment: str = "production",
    ) -> list[dict[str, Any]]:
        with self._database.connection() as connection:
            return list(
                connection.execute(
                    """
                    SELECT * FROM deployments
                    WHERE model = %s
                      AND environment = %s
                      AND occurred_at >= %s
                      AND occurred_at <= %s
                    ORDER BY occurred_at DESC, created_at DESC
                    """,
                    (model, environment, start, end),
                ).fetchall()
            )

    def latest_state(
        self,
        model: str,
        version: str,
        environment: str = "production",
        deployment: str | None = None,
    ) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                """
                SELECT * FROM deployments
                WHERE model = %s
                  AND version = %s
                  AND environment = %s
                  AND (%s::text IS NULL OR deployment = %s::text)
                ORDER BY occurred_at DESC, created_at DESC
                LIMIT 1
                """,
                (model, version, environment, deployment, deployment),
            ).fetchone()
