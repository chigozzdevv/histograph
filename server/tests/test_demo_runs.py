from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import pytest

from histograph.demo_runs.worker import DemoRunWorker


class FakeRuns:
    def __init__(self) -> None:
        self.run_id = uuid4()
        self.queued = True
        self.recovery_ready = False
        self.emitted: tuple[Any, ...] | None = None
        self.recovery_emitted: tuple[Any, ...] | None = None
        self.failed: str | None = None
        self.refreshed = 0

    def active(self) -> list[dict[str, Any]]:
        return [{"id": uuid4()}]

    def claim_queued(self, worker_id, now, limit, lease_seconds):
        assert (worker_id, limit, lease_seconds) == ("demo-worker", 1, 60)
        return [{"id": self.run_id}] if self.queued else []

    def claim_recovery_ready(self, worker_id, now, limit, lease_seconds):
        assert (worker_id, limit, lease_seconds) == ("demo-worker", 1, 60)
        return [{"id": self.run_id}] if self.recovery_ready else []

    def refresh(self, run_id):
        self.refreshed += 1
        return None

    def mark_emitted(self, run_id, monitor_id, result):
        self.emitted = (run_id, monitor_id, result)

    def mark_recovery_emitted(self, run_id, result):
        self.recovery_emitted = (run_id, result)

    def fail(self, run_id, error):
        self.failed = error


class FakeExecutor:
    def __init__(self, monitor_id):
        self.monitor_id = monitor_id

    async def emit(self) -> dict[str, Any]:
        return {"monitor_id": str(self.monitor_id), "status": "awaiting_continuous_worker"}

    async def emit_recovery(self) -> dict[str, Any]:
        return {"status": "fresh_recovery_evidence_emitted", "routing_counts": {"v1": 1000}}


@pytest.mark.asyncio
async def test_demo_worker_claims_once_and_persists_the_monitor_link() -> None:
    runs = FakeRuns()
    monitor_id = uuid4()
    worker = DemoRunWorker(
        "demo-worker",
        runs,
        FakeExecutor(monitor_id),
        batch_size=1,
        lease_seconds=60,
    )

    assert await worker.run_once(datetime(2026, 8, 9, tzinfo=UTC)) == 1
    assert runs.refreshed == 1
    assert runs.failed is None
    assert runs.emitted is not None
    assert runs.emitted[:2] == (runs.run_id, monitor_id)


@pytest.mark.asyncio
async def test_demo_worker_emits_fresh_recovery_traffic_once_verification_is_due() -> None:
    runs = FakeRuns()
    runs.queued = False
    runs.recovery_ready = True
    worker = DemoRunWorker(
        "demo-worker",
        runs,
        FakeExecutor(uuid4()),
        batch_size=1,
        lease_seconds=60,
    )

    assert await worker.run_once(datetime(2026, 8, 9, tzinfo=UTC)) == 1
    assert runs.failed is None
    assert runs.recovery_emitted == (
        runs.run_id,
        {"status": "fresh_recovery_evidence_emitted", "routing_counts": {"v1": 1000}},
    )
