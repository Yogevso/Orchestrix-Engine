"""Scheduler process — recovers stuck jobs, marks stale workers, fires recurring jobs."""

import asyncio
import logging
import signal

from orchestrix.database import async_session_factory
from orchestrix.engine import core

logger = logging.getLogger(__name__)


class SchedulerProcess:
    def __init__(self, check_interval: float = 5.0):
        self.check_interval = check_interval
        self._shutdown = asyncio.Event()

    async def run(self) -> None:
        logger.info("Scheduler starting (check every %.1fs)", self.check_interval)

        while not self._shutdown.is_set():
            try:
                await self._tick()
            except Exception:
                logger.exception("Scheduler tick error")

            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=self.check_interval)
                break
            except asyncio.TimeoutError:
                pass

        logger.info("Scheduler shutting down")

    async def _tick(self) -> None:
        async with async_session_factory() as session:
            # 1. Recover stuck jobs (expired leases)
            recovered = await core.recover_stuck_jobs(session)
            if recovered:
                logger.info("Recovered %d stuck job(s)", recovered)

            # 2. Mark stale workers
            stale = await core.mark_stale_workers(session)
            if stale:
                logger.info("Marked %d worker(s) as offline", stale)

            # 3. Fire due recurring jobs
            fired = await core.tick_recurring_jobs(session)
            if fired:
                logger.info("Fired %d recurring job(s)", fired)

            # 4. Advance workflow steps
            from orchestrix.engine.workflows import advance_all_pending_runs
            advanced = await advance_all_pending_runs(session)
            if advanced:
                logger.info("Advanced %d workflow step(s)", advanced)

    def shutdown(self) -> None:
        self._shutdown.set()


async def run_scheduler(check_interval: float = 5.0) -> None:
    scheduler = SchedulerProcess(check_interval=check_interval)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, scheduler.shutdown)
        except NotImplementedError:
            pass

    await scheduler.run()


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Orchestrix Scheduler")
    parser.add_argument("--interval", type=float, default=5.0, help="Check interval in seconds")
    args = parser.parse_args()

    asyncio.run(run_scheduler(check_interval=args.interval))


if __name__ == "__main__":
    main()
