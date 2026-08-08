from typing import Any
from uuid import UUID, uuid4

from psycopg.types.json import Jsonb

from histograph.models.types import ModelDefinition
from histograph.storage.postgres import PostgresDatabase


class ModelRepository:
    def __init__(self, database: PostgresDatabase):
        self._database = database

    def save(self, model: ModelDefinition) -> UUID:
        model_id = uuid4()
        with self._database.connection() as connection:
            record = connection.execute(
                """
                INSERT INTO models (
                    id, name, task, positive_class, positive_actual, datahub_urn
                ) VALUES (%s, %s, %s, %s, %s, %s)
                ON CONFLICT (name) DO UPDATE SET
                    task = EXCLUDED.task,
                    positive_class = EXCLUDED.positive_class,
                    positive_actual = EXCLUDED.positive_actual,
                    datahub_urn = EXCLUDED.datahub_urn,
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    model_id,
                    model.name,
                    model.task,
                    model.positive_class,
                    Jsonb(model.positive_actual),
                    model.datahub_urn,
                ),
            ).fetchone()
            connection.commit()
        if record is None:
            raise RuntimeError("Model registration did not return an identifier")
        return record["id"]

    def get(self, name: str) -> dict[str, Any] | None:
        with self._database.connection() as connection:
            return connection.execute(
                "SELECT * FROM models WHERE name = %s", (name,)
            ).fetchone()
