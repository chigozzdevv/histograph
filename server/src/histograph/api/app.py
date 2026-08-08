from contextlib import asynccontextmanager

from fastapi import FastAPI

from histograph.api.routes import (
    detection,
    events,
    health,
    incidents,
    investigations,
    models,
    monitors,
)
from histograph.deployments.repository import DeploymentRepository
from histograph.incidents.repository import IncidentRepository
from histograph.models.repository import ModelRepository
from histograph.monitors.repository import MonitorRepository
from histograph.settings import Settings, get_settings
from histograph.storage.clickhouse import ClickHouseStore
from histograph.storage.postgres import PostgresDatabase


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = PostgresDatabase(resolved_settings.postgres_dsn)
    deployments_repository = DeploymentRepository(database)
    monitors_repository = MonitorRepository(database)
    incidents_repository = IncidentRepository(database)
    models_repository = ModelRepository(database)
    telemetry = ClickHouseStore(
        host=resolved_settings.clickhouse_host,
        port=resolved_settings.clickhouse_port,
        database=resolved_settings.clickhouse_database,
        user=resolved_settings.clickhouse_user,
        password=resolved_settings.clickhouse_password,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.initialize()
        telemetry.initialize()
        yield
        telemetry.close()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.deployments = deployments_repository
    app.state.monitors = monitors_repository
    app.state.incidents = incidents_repository
    app.state.models = models_repository
    app.state.telemetry = telemetry
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(models.router)
    app.include_router(monitors.router)
    app.include_router(detection.router)
    app.include_router(incidents.router)
    app.include_router(investigations.router)
    return app


app = create_app()
