from contextlib import asynccontextmanager

from fastapi import FastAPI

from histograph.api.routes import detection, events, health, incidents, investigations, monitors
from histograph.settings import Settings, get_settings
from histograph.storage.clickhouse import ClickHouseStore
from histograph.storage.postgres import PostgresStore


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    control = PostgresStore(resolved_settings.postgres_dsn)
    telemetry = ClickHouseStore(
        host=resolved_settings.clickhouse_host,
        port=resolved_settings.clickhouse_port,
        database=resolved_settings.clickhouse_database,
        user=resolved_settings.clickhouse_user,
        password=resolved_settings.clickhouse_password,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        control.initialize()
        telemetry.initialize()
        yield
        telemetry.close()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.control = control
    app.state.telemetry = telemetry
    app.include_router(health.router)
    app.include_router(events.router)
    app.include_router(monitors.router)
    app.include_router(detection.router)
    app.include_router(incidents.router)
    app.include_router(investigations.router)
    return app


app = create_app()
