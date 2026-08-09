from dataclasses import dataclass
from os import getpid
from socket import gethostname
from uuid import uuid4

from histograph.changes.repository import ChangeRepository
from histograph.changes.service import ReleaseContextService
from histograph.demo_runs.repository import DemoRunRepository
from histograph.demo_runs.worker import DemoRunWorker, ReferenceDemoExecutor
from histograph.deployments.repository import DeploymentRepository
from histograph.detection.service import MonitorEvaluationService
from histograph.incidents.repository import IncidentRepository
from histograph.integrations.datahub.client import DataHubMcpClient
from histograph.integrations.github.client import build_github_client
from histograph.integrations.github.repository import GitOpsRepository
from histograph.integrations.github.workers import GitOpsProposalWorker
from histograph.models.repository import ModelRepository
from histograph.monitors.repository import MonitorRepository
from histograph.remediation.adapters import RemediationAdapter, WebhookRemediationAdapter
from histograph.remediation.repository import RemediationRepository
from histograph.remediation.service import RemediationService
from histograph.settings import Settings
from histograph.storage.clickhouse import ClickHouseDatabase
from histograph.storage.postgres import PostgresDatabase
from histograph.telemetry.repository import TelemetryRepository
from histograph.workers.services import (
    ActionWorker,
    ControlPlaneWorker,
    InvestigationWorker,
    MonitorWorker,
    RecoveryEvaluator,
    RecoveryWorker,
)


@dataclass
class WorkerRuntime:
    worker: ControlPlaneWorker
    clickhouse: ClickHouseDatabase

    def close(self) -> None:
        self.clickhouse.close()


def build_worker_runtime(settings: Settings) -> WorkerRuntime:
    database = PostgresDatabase(settings.postgres_dsn)
    database.migrate()
    clickhouse = ClickHouseDatabase(
        host=settings.clickhouse_host,
        port=settings.clickhouse_port,
        database=settings.clickhouse_database,
        user=settings.clickhouse_user,
        password=settings.clickhouse_password,
    )
    clickhouse.migrate()
    monitors = MonitorRepository(database)
    incidents = IncidentRepository(database)
    models = ModelRepository(database)
    deployments = DeploymentRepository(database)
    changes = ChangeRepository(database)
    remediation = RemediationRepository(database)
    gitops = GitOpsRepository(database)
    demo_runs = DemoRunRepository(database)
    telemetry = TelemetryRepository(clickhouse)
    evaluation = MonitorEvaluationService(monitors, deployments, models, telemetry, incidents)
    release_context = ReleaseContextService(changes, deployments)
    datahub = DataHubMcpClient(settings)
    worker_id = f"{gethostname()}-{getpid()}-{uuid4().hex[:8]}"
    adapters: dict[str, RemediationAdapter] = {}
    if settings.remediation_webhook_url is not None:
        adapters["webhook"] = WebhookRemediationAdapter(
            settings.remediation_webhook_url,
            settings.remediation_webhook_token,
            settings.remediation_webhook_timeout_seconds,
        )
    common = {
        "batch_size": settings.worker_batch_size,
        "lease_seconds": settings.worker_lease_seconds,
    }
    monitor_worker = MonitorWorker(
        worker_id,
        monitors,
        evaluation,
        retry_seconds=settings.worker_retry_seconds,
        **common,
    )
    investigation_worker = InvestigationWorker(
        worker_id,
        incidents,
        models,
        datahub,
        release_context,
        RemediationService(remediation, gitops),
        retry_seconds=settings.worker_retry_seconds,
        **common,
    )
    action_worker = ActionWorker(worker_id, remediation, adapters, **common)
    gitops_worker = GitOpsProposalWorker(
        worker_id,
        gitops,
        build_github_client(settings),
        retry_seconds=settings.worker_retry_seconds,
        **common,
    )
    recovery_worker = RecoveryWorker(
        worker_id,
        remediation,
        incidents,
        models,
        datahub,
        release_context,
        RecoveryEvaluator(deployments, changes, evaluation),
        write_back=settings.datahub_mcp_mutations_enabled,
        retry_seconds=settings.worker_retry_seconds,
        **common,
    )
    demo_worker = DemoRunWorker(
        worker_id,
        demo_runs,
        ReferenceDemoExecutor(settings),
        **common,
    )
    return WorkerRuntime(
        worker=ControlPlaneWorker(
            monitor_worker,
            investigation_worker,
            action_worker,
            recovery_worker,
            gitops=gitops_worker,
            demo=demo_worker,
        ),
        clickhouse=clickhouse,
    )
