"""Worker process — polls for jobs, executes handlers, sends heartbeats."""

import asyncio
import logging
import signal
import uuid

from orchestrix.config import settings
from orchestrix.database import async_session_factory
from orchestrix.engine import core
from orchestrix.worker.handlers import HANDLERS

logger = logging.getLogger(__name__)


class WorkerProcess:
    def __init__(self, name: str, queues: list[str] | None = None):
        self.name = name
        self.queues = queues or ["default"]
        self.worker_id: uuid.UUID | None = None
        self._shutdown = asyncio.Event()

    async def register(self) -> None:
        async with async_session_factory() as session:
            worker = await core.register_worker(session, name=self.name, queues=self.queues)
            self.worker_id = worker.id
            logger.info("Worker registered: %s (id=%s, queues=%s)", self.name, self.worker_id, self.queues)

    async def run(self) -> None:
        await self.register()

        logger.info("Worker %s starting poll loop", self.name)
        while not self._shutdown.is_set():
            try:
                await self._poll_and_execute()
            except Exception:
                logger.exception("Unexpected error in poll loop")
            try:
                await asyncio.wait_for(self._shutdown.wait(), timeout=settings.worker_poll_interval)
                break  # shutdown was set
            except asyncio.TimeoutError:
                pass  # normal — just loop again

        logger.info("Worker %s shutting down", self.name)

    async def _poll_and_execute(self) -> None:
        async with async_session_factory() as session:
            job = await core.poll_job(session, self.worker_id, self.queues)
            if not job:
                return

            logger.info("Leased job %s (type=%s)", job.id, job.type)

            # Transition to RUNNING
            job = await core.start_job(session, job.id, self.worker_id)
            if not job:
                logger.warning("Failed to start job — may have been reclaimed")
                return

        # Execute with heartbeat
        await self._execute_with_heartbeat(job.id, job.type, job.payload)

    async def _execute_with_heartbeat(self, job_id: uuid.UUID, job_type: str, payload: dict) -> None:
        heartbeat_task = asyncio.create_task(self._heartbeat_loop(job_id))

        try:
            handler = HANDLERS.get(job_type)
            if not handler:
                raise RuntimeError(f"No handler registered for job type: {job_type}")

            result = await handler(payload)

            # Success
            async with async_session_factory() as session:
                job = await core.complete_job(session, job_id, self.worker_id, result)
                # If this job is part of a workflow, advance the DAG
                if job and job.workflow_step_id:
                    from orchestrix.engine.workflows import on_job_completed
                    await on_job_completed(session, job)
            logger.info("Job %s succeeded", job_id)

        except Exception as exc:
            # Failure
            logger.error("Job %s failed: %s", job_id, exc)
            async with async_session_factory() as session:
                job = await core.fail_job(session, job_id, self.worker_id, str(exc))
                # If this job is part of a workflow, notify the DAG
                if job and job.workflow_step_id:
                    from orchestrix.engine.workflows import on_job_failed
                    await on_job_failed(session, job

        finally:
            heartbeat_task.cancel()
            try:
                await heartbeat_task
            except asyncio.CancelledError:
                pass

    async def _heartbeat_loop(self, job_id: uuid.UUID) -> None:
        while True:
            await asyncio.sleep(settings.heartbeat_interval_seconds)
            try:
                async with async_session_factory() as session:
                    await core.heartbeat_job(session, job_id, self.worker_id)
                    await core.worker_heartbeat(session, self.worker_id)
                logger.debug("Heartbeat sent for job %s", job_id)
            except Exception:
                logger.exception("Heartbeat failed for job %s", job_id)

    def shutdown(self) -> None:
        self._shutdown.set()


async def run_worker(name: str = "worker-1", queues: list[str] | None = None) -> None:
    worker = WorkerProcess(name=name, queues=queues)

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, worker.shutdown)
        except NotImplementedError:
            # Windows doesn't support add_signal_handler
            pass

    await worker.run()


def main() -> None:
    import argparse

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    parser = argparse.ArgumentParser(description="Orchestrix Worker")
    parser.add_argument("--name", default="worker-1", help="Worker name")
    parser.add_argument("--queues", nargs="+", default=["default"], help="Queues to poll")
    args = parser.parse_args()

    asyncio.run(run_worker(name=args.name, queues=args.queues))


if __name__ == "__main__":
    main()
