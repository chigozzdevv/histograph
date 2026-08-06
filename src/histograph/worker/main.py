import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from histograph.api.config import get_settings
from histograph.api.database.session import create_database
from histograph.github import GitHubAppClient
from histograph.runner import Runner
from histograph.security import EnvelopeCipher
from histograph.storage import ArtifactStore
from histograph.worker.activities import RunActivities
from histograph.worker.incidents import IncidentManager
from histograph.workflows import RunWorkflow, ScheduledRunWorkflow


async def run_worker() -> None:
    settings = get_settings()
    engine, session_factory = create_database(settings)
    cipher = EnvelopeCipher.from_config(settings.encryption_keys.get_secret_value())
    artifact_store = ArtifactStore(
        endpoint_url=settings.s3_endpoint_url,
        bucket=settings.s3_bucket,
        region=settings.s3_region,
        access_key_id=(
            settings.s3_access_key_id.get_secret_value() if settings.s3_access_key_id else None
        ),
        secret_access_key=(
            settings.s3_secret_access_key.get_secret_value()
            if settings.s3_secret_access_key
            else None
        ),
    )
    await artifact_store.ensure_bucket()
    client = await Client.connect(
        settings.temporal_address,
        namespace=settings.temporal_namespace,
    )
    github_client = (
        GitHubAppClient(
            app_id=settings.github_app_id,
            private_key=settings.github_private_key.get_secret_value(),
            api_url=settings.github_api_url,
            api_version=settings.github_api_version,
        )
        if settings.github_app_id and settings.github_private_key
        else None
    )
    activities = RunActivities(
        session_factory,
        cipher,
        artifact_store,
        Runner(),
        github_client=github_client,
        incident_manager=IncidentManager(
            session_factory,
            cipher,
            settings.public_app_url,
        ),
    )
    worker = Worker(
        client,
        task_queue=settings.temporal_task_queue,
        workflows=[RunWorkflow, ScheduledRunWorkflow],
        activities=[
            activities.plan_run,
            activities.execute_selected_tests,
            activities.report_run,
            activities.cancel_run,
            activities.fail_run,
            activities.create_scheduled_run,
        ],
    )
    try:
        await worker.run()
    finally:
        if github_client:
            await github_client.close()
        await engine.dispose()


def main() -> None:
    asyncio.run(run_worker())


if __name__ == "__main__":
    main()
