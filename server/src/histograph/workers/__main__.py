import asyncio
import logging

from histograph.core.time import utc_now
from histograph.settings import Settings
from histograph.workers.runtime import build_worker_runtime


async def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    settings = Settings()
    runtime = build_worker_runtime(settings)
    try:
        await runtime.worker.run_forever(utc_now, settings.worker_poll_interval_seconds)
    finally:
        runtime.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
