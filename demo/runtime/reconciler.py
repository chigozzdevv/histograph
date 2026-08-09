import asyncio
import logging
from typing import Any, Protocol

import httpx

from demo.runtime.state import RuntimeStateStore
from histograph.core.time import utc_now
from histograph.integrations.github.client import GitHubDeploymentClient
from histograph.integrations.github.manifest import parse_manifest

logger = logging.getLogger(__name__)


class RuntimeControlClient(Protocol):
    async def state(self) -> dict[str, Any]: ...

    async def apply(self, revision: str, content: str) -> dict[str, Any]: ...


class ReferenceRuntimeClient:
    def __init__(
        self,
        base_url: str,
        control_token: str,
        *,
        timeout_seconds: float = 60,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._control_token = control_token
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def state(self) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.get("/v1/runtime")
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Reference runtime returned an invalid state response")
        return payload

    async def apply(self, revision: str, content: str) -> dict[str, Any]:
        async with self._client() as client:
            response = await client.post(
                "/v1/deployments/apply",
                json={"revision": revision, "content": content},
                headers={"Authorization": f"Bearer {self._control_token}"},
            )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError("Reference runtime returned an invalid apply response")
        return payload

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
        )


class ReferenceDeploymentReconciler:
    def __init__(
        self,
        connection: dict[str, Any],
        github: GitHubDeploymentClient,
        runtime: RuntimeControlClient,
        state: RuntimeStateStore,
        *,
        log_url: str | None = None,
    ):
        self._connection = connection
        self._github = github
        self._runtime = runtime
        self._state = state
        self._log_url = log_url

    async def run_once(self) -> dict[str, Any]:
        repository_file = await self._github.get_file(self._connection)
        manifest = parse_manifest(repository_file.content)
        deployment_name = manifest.metadata.name
        previous = self._state.reconciler_deployment(deployment_name)
        if (
            previous is not None
            and previous["revision"] == repository_file.revision
            and previous["status"] == "success"
        ):
            return {"status": "unchanged", "revision": repository_file.revision}

        if previous is None or previous["revision"] != repository_file.revision:
            deployment = await self._github.create_deployment(
                self._connection,
                revision=repository_file.revision,
                environment=manifest.spec.environment,
                payload={
                    "source": "histograph-reference-reconciler",
                    "manifest_path": self._connection["manifest_path"],
                    "deployment": deployment_name,
                },
            )
            if deployment.revision != repository_file.revision:
                raise RuntimeError("GitHub deployment resolved a different repository revision")
            deployment_id = deployment.id
            self._save(deployment_name, repository_file.revision, deployment_id, "created")
        else:
            deployment_id = int(previous["github_deployment_id"])

        await self._github.create_deployment_status(
            self._connection,
            deployment_id=deployment_id,
            state="in_progress",
            environment=manifest.spec.environment,
            description="Applying model deployment manifest",
            log_url=self._log_url,
        )
        self._save(deployment_name, repository_file.revision, deployment_id, "in_progress")
        try:
            runtime_state = await self._runtime.state()
            if runtime_state.get("revision") != repository_file.revision:
                await self._runtime.apply(repository_file.revision, repository_file.content)
            await self._github.create_deployment_status(
                self._connection,
                deployment_id=deployment_id,
                state="success",
                environment=manifest.spec.environment,
                description="Model deployment manifest applied",
                log_url=self._log_url,
            )
            self._save(deployment_name, repository_file.revision, deployment_id, "success")
            return {
                "status": "applied",
                "revision": repository_file.revision,
                "github_deployment_id": deployment_id,
            }
        except Exception as error:
            try:
                await self._github.create_deployment_status(
                    self._connection,
                    deployment_id=deployment_id,
                    state="failure",
                    environment=manifest.spec.environment,
                    description="Model deployment manifest failed",
                    log_url=self._log_url,
                )
            finally:
                self._save(
                    deployment_name,
                    repository_file.revision,
                    deployment_id,
                    "failed",
                    str(error),
                )
            raise

    async def run_forever(self, poll_seconds: float) -> None:
        while True:
            try:
                result = await self.run_once()
                if result["status"] != "unchanged":
                    logger.info("reference deployment reconciliation completed", extra=result)
            except Exception:
                logger.exception("reference deployment reconciliation failed")
            await asyncio.sleep(poll_seconds)

    def _save(
        self,
        deployment: str,
        revision: str,
        github_deployment_id: int,
        status: str,
        error: str | None = None,
    ) -> None:
        self._state.save_reconciler_deployment(
            deployment,
            revision,
            github_deployment_id,
            status,
            utc_now(),
            error,
        )
