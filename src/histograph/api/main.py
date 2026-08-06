from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError

from histograph.api.config import Settings, get_settings
from histograph.api.database.session import create_database
from histograph.api.routes.github import router as github_router
from histograph.api.routes.health import router as health_router
from histograph.api.routes.integrations import router as integrations_router
from histograph.api.routes.operations import router as operations_router
from histograph.api.routes.organizations import router as organizations_router
from histograph.api.routes.projects import router as projects_router
from histograph.api.routes.runs import router as runs_router
from histograph.api.routes.tests import router as tests_router
from histograph.api.routes.triggers import router as triggers_router
from histograph.api.security import Authenticator
from histograph.api.services.orchestration import Orchestrator, TemporalOrchestrator
from histograph.github import GitHubAppClient
from histograph.security import EnvelopeCipher, TokenManager


def create_app(
    settings: Settings | None = None,
    orchestrator: Orchestrator | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    engine, session_factory = create_database(resolved_settings)
    envelope_cipher = EnvelopeCipher.from_config(
        resolved_settings.encryption_keys.get_secret_value()
    )
    token_manager = TokenManager(resolved_settings.token_pepper.get_secret_value())
    github_client = (
        GitHubAppClient(
            app_id=resolved_settings.github_app_id,
            private_key=resolved_settings.github_private_key.get_secret_value(),
            api_url=resolved_settings.github_api_url,
            api_version=resolved_settings.github_api_version,
        )
        if resolved_settings.github_app_id and resolved_settings.github_private_key
        else None
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        await _verify_migrated_database(session_factory)
        active_orchestrator = orchestrator or await TemporalOrchestrator.connect(resolved_settings)
        app.state.orchestrator = active_orchestrator
        try:
            yield
        finally:
            if orchestrator is None:
                await active_orchestrator.close()
            if github_client:
                await github_client.close()
            await engine.dispose()

    app = FastAPI(title="Histograph API", version="0.2.0", lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.session_factory = session_factory
    app.state.envelope_cipher = envelope_cipher
    app.state.token_manager = token_manager
    app.state.authenticator = Authenticator(resolved_settings, session_factory, token_manager)
    app.state.github_client = github_client
    if orchestrator is not None:
        app.state.orchestrator = orchestrator
    app.add_middleware(
        CORSMiddleware,
        allow_origins=resolved_settings.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        supplied = request.headers.get("x-request-id", "")
        request.state.request_id = supplied[:64] if supplied else uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response

    app.include_router(health_router, prefix="/v1")
    app.include_router(organizations_router, prefix="/v1")
    app.include_router(operations_router, prefix="/v1")
    app.include_router(github_router, prefix="/v1")
    app.include_router(projects_router, prefix="/v1")
    app.include_router(integrations_router, prefix="/v1")
    app.include_router(tests_router, prefix="/v1")
    app.include_router(runs_router, prefix="/v1")
    app.include_router(triggers_router, prefix="/v1")
    return app


async def _verify_migrated_database(session_factory) -> None:
    try:
        async with session_factory() as session:
            revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    except ProgrammingError as error:
        raise RuntimeError("Database migrations have not been applied") from error
    if not revision:
        raise RuntimeError("Database migration revision is unavailable")


def app_factory() -> FastAPI:
    return create_app()
