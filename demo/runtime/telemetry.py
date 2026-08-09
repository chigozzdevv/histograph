import asyncio
import logging
from datetime import datetime
from typing import Any, Protocol

import httpx

from demo.runtime.state import RuntimeStateStore
from histograph.core.time import ensure_utc, utc_now

logger = logging.getLogger(__name__)


class TelemetrySink(Protocol):
    async def send(self, event_type: str, payload: dict[str, Any]) -> None: ...


class HistographTelemetrySink:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        transport: httpx.AsyncBaseTransport | None = None,
    ):
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def send(self, event_type: str, payload: dict[str, Any]) -> None:
        paths = {
            "predictions": "/v1/events/predictions/batch",
            "actuals": "/v1/events/actuals/batch",
            "deployment": "/v1/events/deployments",
            "change": "/v1/events/changes",
        }
        path = paths.get(event_type)
        if path is None:
            raise ValueError(f"Unsupported telemetry outbox event: {event_type}")
        async with httpx.AsyncClient(
            base_url=self._base_url,
            timeout=self._timeout_seconds,
            transport=self._transport,
        ) as client:
            response = await client.post(path, json=payload)
        response.raise_for_status()


class TelemetryWorker:
    def __init__(
        self,
        state: RuntimeStateStore,
        sink: TelemetrySink,
        *,
        batch_size: int,
        retry_seconds: int,
    ):
        self._state = state
        self._sink = sink
        self._batch_size = batch_size
        self._retry_seconds = retry_seconds

    async def run_once(self, now: datetime | None = None) -> int:
        timestamp = ensure_utc(now or utc_now())
        records = self._state.due(timestamp, self._batch_size)
        for record in records:
            try:
                await self._sink.send(record["event_type"], record["payload"])
                self._state.complete(int(record["id"]))
            except Exception as error:
                logger.warning(
                    "reference runtime telemetry delivery failed",
                    extra={"event_id": record["id"], "event_type": record["event_type"]},
                    exc_info=True,
                )
                self._state.fail(int(record["id"]), str(error), timestamp, self._retry_seconds)
        return len(records)

    async def run_forever(self, poll_seconds: float) -> None:
        while True:
            await self.run_once()
            await asyncio.sleep(poll_seconds)
