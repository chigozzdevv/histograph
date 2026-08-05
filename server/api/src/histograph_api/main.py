from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from histograph_runner import Runner

from histograph_api.config import Settings, get_settings
from histograph_api.database.base import Base
from histograph_api.database.session import create_database
from histograph_api.routes.health import router as health_router
from histograph_api.routes.runs import router as runs_router


def create_app(settings: Settings | None = None, runner: Runner | None = None) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine, session_factory = create_database(resolved_settings)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        yield
        await engine.dispose()

    app = FastAPI(title="Histograph API", version="0.1.0", lifespan=lifespan)
    app.state.session_factory = session_factory
    app.state.runner = runner or Runner()
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization"],
    )
    app.include_router(health_router, prefix="/v1")
    app.include_router(runs_router, prefix="/v1")
    return app


app = create_app()
