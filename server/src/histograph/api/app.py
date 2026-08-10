from contextlib import asynccontextmanager

from fastapi import FastAPI

from histograph.actuals.repository import ActualRepository
from histograph.actuals.service import ActualService
from histograph.api.routes import (
    actuals,
    changes,
    demo,
    deployments,
    detection,
    github,
    health,
    incidents,
    investigations,
    models,
    monitors,
    predictions,
    product,
    remediation,
)
from histograph.changes.repository import ChangeRepository
from histograph.changes.service import ChangeService, ReleaseContextService
from histograph.demo_runs.repository import DemoRunRepository
from histograph.deployments.repository import DeploymentRepository
from histograph.deployments.service import DeploymentService
from histograph.incidents.repository import IncidentRepository
from histograph.integrations.github.client import GitHubClient, build_github_client
from histograph.integrations.github.repository import GitOpsRepository
from histograph.integrations.github.service import (
    GitHubIntegrationService,
    GitHubWebhookService,
)
from histograph.models.repository import ModelRepository
from histograph.monitors.repository import MonitorRepository
from histograph.product.rate_limits import RateLimitRepository
from histograph.product.repository import ProductRepository
from histograph.product.runtime import RuntimeConnector
from histograph.remediation.repository import RemediationRepository
from histograph.settings import Settings, get_settings
from histograph.storage.clickhouse import ClickHouseDatabase
from histograph.storage.postgres import PostgresDatabase
from histograph.telemetry.repository import TelemetryRepository
from histograph.telemetry.service import TelemetryService


def create_app(
    settings: Settings | None = None,
    github_client: GitHubClient | None = None,
    runtime_connector: RuntimeConnector | None = None,
) -> FastAPI:
    resolved_settings = settings or get_settings()
    database = PostgresDatabase(resolved_settings.postgres_dsn)
    changes_repository = ChangeRepository(database)
    deployments_repository = DeploymentRepository(database)
    monitors_repository = MonitorRepository(database)
    incidents_repository = IncidentRepository(database)
    remediation_repository = RemediationRepository(database)
    models_repository = ModelRepository(database)
    gitops_repository = GitOpsRepository(database)
    demo_runs_repository = DemoRunRepository(database)
    product_repository = ProductRepository(database)
    rate_limits_repository = RateLimitRepository(database)
    resolved_runtime_connector = runtime_connector or RuntimeConnector(
        resolved_settings.playground_allowed_hosts,
        resolved_settings.reference_control_token,
        resolved_settings.playground_timeout_seconds,
    )
    resolved_github_client = github_client or build_github_client(resolved_settings)
    clickhouse = ClickHouseDatabase(
        host=resolved_settings.clickhouse_host,
        port=resolved_settings.clickhouse_port,
        database=resolved_settings.clickhouse_database,
        user=resolved_settings.clickhouse_user,
        password=resolved_settings.clickhouse_password,
    )
    telemetry_repository = TelemetryRepository(clickhouse)
    actuals_repository = ActualRepository(clickhouse)
    predictions_service = TelemetryService(telemetry_repository)
    actuals_service = ActualService(actuals_repository)
    deployment_service = DeploymentService(deployments_repository, (gitops_repository,))
    change_service = ChangeService(changes_repository, (gitops_repository,))
    github_integration = GitHubIntegrationService(
        gitops_repository,
        models_repository,
        resolved_github_client,
        resolved_runtime_connector,
        resolved_settings.demo_runtime_url,
    )
    github_webhooks = GitHubWebhookService(
        gitops_repository, remediation_repository, github_integration
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        database.migrate()
        clickhouse.migrate()
        yield
        clickhouse.close()

    app = FastAPI(title=resolved_settings.app_name, lifespan=lifespan)
    app.state.settings = resolved_settings
    app.state.database = database
    app.state.deployments = deployments_repository
    app.state.deployment_ingestion = deployment_service
    app.state.changes = changes_repository
    app.state.change_ingestion = change_service
    app.state.release_context = ReleaseContextService(changes_repository, deployments_repository)
    app.state.monitors = monitors_repository
    app.state.incidents = incidents_repository
    app.state.remediation = remediation_repository
    app.state.gitops = gitops_repository
    app.state.demo_runs = demo_runs_repository
    app.state.github_client = resolved_github_client
    app.state.github_integration = github_integration
    app.state.github_webhooks = github_webhooks
    app.state.product = product_repository
    app.state.rate_limits = rate_limits_repository
    app.state.runtime_connector = resolved_runtime_connector
    app.state.models = models_repository
    app.state.clickhouse = clickhouse
    app.state.telemetry = telemetry_repository
    app.state.predictions = predictions_service
    app.state.actuals = actuals_service
    app.include_router(health.router)
    app.include_router(predictions.router)
    app.include_router(actuals.router)
    app.include_router(deployments.router)
    app.include_router(changes.router)
    app.include_router(models.router)
    app.include_router(monitors.router)
    app.include_router(detection.router)
    app.include_router(incidents.router)
    app.include_router(investigations.router)
    app.include_router(remediation.router)
    app.include_router(github.router)
    app.include_router(product.router)
    app.include_router(demo.router)
    return app


app = create_app()
