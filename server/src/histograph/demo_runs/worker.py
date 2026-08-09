import asyncio
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID

from demo.scenario import emit_runtime_canary_traffic

from histograph.settings import Settings


class DemoRunStore(Protocol):
    def active(self) -> list[dict[str, Any]]: ...

    def claim_queued(
        self, worker_id: str, now: datetime, limit: int, lease_seconds: int
    ) -> list[dict[str, Any]]: ...

    def refresh(self, run_id: UUID) -> dict[str, Any] | None: ...

    def mark_emitted(self, run_id: UUID, monitor_id: UUID, result: dict[str, Any]) -> None: ...

    def fail(self, run_id: UUID, error: str) -> None: ...


class DemoRunExecutor(Protocol):
    async def emit(self) -> dict[str, Any]: ...


class ReferenceDemoExecutor:
    def __init__(self, settings: Settings):
        self._settings = settings

    async def emit(self) -> dict[str, Any]:
        return await asyncio.to_thread(
            emit_runtime_canary_traffic,
            self._settings.demo_api_url,
            self._settings.demo_runtime_url,
            self._settings.demo_replay_path,
            self._settings.demo_artifact_path,
            sample_size=self._settings.demo_sample_size,
            outbox_wait_seconds=self._settings.demo_outbox_wait_seconds,
        )


class DemoRunWorker:
    def __init__(
        self,
        worker_id: str,
        runs: DemoRunStore,
        executor: DemoRunExecutor,
        *,
        batch_size: int,
        lease_seconds: int,
    ):
        self._worker_id = worker_id
        self._runs = runs
        self._executor = executor
        self._batch_size = batch_size
        self._lease_seconds = lease_seconds

    async def run_once(self, now: datetime) -> int:
        for active in self._runs.active():
            self._runs.refresh(active["id"])
        records = self._runs.claim_queued(
            self._worker_id, now, self._batch_size, self._lease_seconds
        )
        for run in records:
            try:
                result = await self._executor.emit()
                self._runs.mark_emitted(run["id"], UUID(str(result["monitor_id"])), result)
            except Exception as error:
                self._runs.fail(run["id"], str(error))
        return len(records)
