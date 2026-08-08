import os
from collections.abc import Generator
from uuid import uuid4

import clickhouse_connect
import pytest
from fastapi.testclient import TestClient
from psycopg import connect, sql

from histograph.api.app import create_app
from histograph.settings import Settings

pytestmark = pytest.mark.skipif(
    os.getenv("HISTOGRAPH_RUN_INTEGRATION") != "1",
    reason="Set HISTOGRAPH_RUN_INTEGRATION=1 to run database integration tests",
)


@pytest.fixture
def integration_settings() -> Generator[Settings]:
    suffix = uuid4().hex
    postgres_database = f"histograph_test_{suffix}"
    clickhouse_database = f"histograph_test_{suffix}"
    admin_dsn = "postgresql://histograph:histograph@localhost:5433/postgres"

    with connect(admin_dsn, autocommit=True) as connection:
        connection.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(postgres_database)))

    settings = Settings(
        postgres_dsn=(
            f"postgresql://histograph:histograph@localhost:5433/{postgres_database}"
        ),
        clickhouse_database=clickhouse_database,
    )
    try:
        yield settings
    finally:
        clickhouse = clickhouse_connect.get_client(
            host=settings.clickhouse_host,
            port=settings.clickhouse_port,
            username=settings.clickhouse_user,
            password=settings.clickhouse_password,
        )
        clickhouse.command(f"DROP DATABASE IF EXISTS {clickhouse_database}")
        clickhouse.close()
        with connect(admin_dsn, autocommit=True) as connection:
            connection.execute(
                sql.SQL("DROP DATABASE IF EXISTS {} WITH (FORCE)").format(
                    sql.Identifier(postgres_database)
                )
            )


def test_binary_monitor_creates_one_auditable_incident(
    integration_settings: Settings,
) -> None:
    with TestClient(create_app(integration_settings)) as client:
        model_response = client.put(
            "/v1/models/fraud",
            json={
                "name": "fraud",
                "task": "binary_classification",
                "positive_class": "blocked",
                "positive_actual": "chargeback",
            },
        )
        assert model_response.status_code == 200

        deployment_response = client.post(
            "/v1/events/deployments",
            json={
                "deployment": "fraud-production",
                "model": "fraud",
                "version": "v1",
                "status": "active",
                "occurred_at": "2026-08-08T10:00:00Z",
            },
        )
        assert deployment_response.status_code == 202

        events = [
            (
                "baseline-1",
                "blocked",
                "chargeback",
                "2026-08-08T11:00:00Z",
                "2026-08-08T11:20:00Z",
            ),
            (
                "baseline-2",
                "allowed",
                "legitimate",
                "2026-08-08T11:10:00Z",
                "2026-08-08T11:21:00Z",
            ),
            (
                "current-1",
                "blocked",
                "legitimate",
                "2026-08-08T11:50:00Z",
                "2026-08-08T11:55:00Z",
            ),
            (
                "current-2",
                "allowed",
                "legitimate",
                "2026-08-08T11:51:00Z",
                "2026-08-08T11:56:00Z",
            ),
        ]
        for prediction_id, predicted_class, actual, observed_at, actual_at in events:
            prediction_response = client.post(
                "/v1/events/predictions",
                json={
                    "prediction_id": prediction_id,
                    "model": "fraud",
                    "version": "v1",
                    "observed_at": observed_at,
                    "predicted_class": predicted_class,
                },
            )
            assert prediction_response.status_code == 202
            actual_response = client.post(
                "/v1/events/actuals",
                json={
                    "prediction_id": prediction_id,
                    "actual": actual,
                    "observed_at": actual_at,
                },
            )
            assert actual_response.status_code == 202

        monitor_response = client.post(
            "/v1/monitors",
            json={
                "model": "fraud",
                "signal": "performance",
                "metric": "accuracy",
                "operator": "lt",
                "threshold": 0.75,
                "minimum_sample_size": 2,
            },
        )
        assert monitor_response.status_code == 201
        monitor_id = monitor_response.json()["id"]

        payload = {"as_of": "2026-08-08T12:00:00Z"}
        first_detection = client.post(
            f"/v1/detection/monitors/{monitor_id}/performance",
            json=payload,
        )
        assert first_detection.status_code == 200
        assert first_detection.json()["status"] == "evaluated"
        assert first_detection.json()["observed_value"] == 0.5
        assert first_detection.json()["triggered"] is True
        incident_id = first_detection.json()["incident_id"]

        repeated_detection = client.post(
            f"/v1/detection/monitors/{monitor_id}/performance",
            json=payload,
        )
        assert repeated_detection.status_code == 200
        assert repeated_detection.json()["incident_id"] == incident_id

        incident_response = client.get(f"/v1/incidents/{incident_id}")
        assert incident_response.status_code == 200
        assert incident_response.json()["status"] == "open"
        assert [event["event_type"] for event in incident_response.json()["timeline"]] == [
            "created"
        ]

        transition_response = client.patch(
            f"/v1/incidents/{incident_id}",
            json={"status": "resolved", "reason": "Model mapping corrected"},
        )
        assert transition_response.status_code == 200
        assert transition_response.json()["status"] == "resolved"
        assert transition_response.json()["resolved_at"] is not None
