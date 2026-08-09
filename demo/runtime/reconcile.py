import asyncio
import logging

from demo.runtime.reconciler import (
    ReferenceDeploymentReconciler,
    ReferenceRuntimeClient,
)
from demo.runtime.settings import ReferenceRuntimeSettings
from demo.runtime.state import RuntimeStateStore
from histograph.integrations.github.client import build_github_client
from histograph.settings import Settings


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    runtime_settings = ReferenceRuntimeSettings()
    histograph_settings = Settings()
    github = build_github_client(histograph_settings)
    if github is None:
        raise RuntimeError("GitHub App ID and private key are required for reconciliation")
    if runtime_settings.control_token is None:
        raise RuntimeError("Reference runtime control token is required for reconciliation")
    connection = _connection(runtime_settings)
    state = RuntimeStateStore(runtime_settings.reconciler_state_path)
    reconciler = ReferenceDeploymentReconciler(
        connection,
        github,
        ReferenceRuntimeClient(
            runtime_settings.runtime_url,
            runtime_settings.control_token,
        ),
        state,
        log_url=f"{runtime_settings.runtime_url.rstrip('/')}/v1/runtime",
    )
    try:
        await reconciler.run_forever(runtime_settings.reconciler_poll_seconds)
    finally:
        state.close()


def _connection(settings: ReferenceRuntimeSettings) -> dict[str, object]:
    required = {
        "installation_id": settings.github_installation_id,
        "repository_owner": settings.github_repository_owner,
        "repository_name": settings.github_repository_name,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        raise RuntimeError(
            "Reference GitHub connection is incomplete: " + ", ".join(sorted(missing))
        )
    return {
        **required,
        "branch": settings.github_branch,
        "manifest_path": settings.github_manifest_path,
    }


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
