"""Core engine logic — job lifecycle, leasing, retries, dead-lettering, recurring jobs."""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import case, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.config import settings
from orchestrix.models.enums import JobEventType, JobStatus, WorkerStatus
from orchestrix.models.tables import Job, JobEvent, QueueConfig, RecurringJob, Worker


def _fire_and_forget(coro):
    """Schedule a coroutine without awaiting — used for WebSocket notifications."""
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(coro)
    except RuntimeError:
        pass  # No event loop — skip notification (e.g. during tests)


# ────────────────────────── helpers ──────────────────────────


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def _emit_event(
    session: AsyncSession,
    job_id: uuid.UUID,
    event_type: JobEventType,
    message: str | None = None,
    metadata: dict | None = None,
) -> None:
    event = JobEvent(job_id=job_id, event_type=event_type, message=message, metadata_=metadata)
    session.add(event)


# ────────────────────────── job creation ──────────────────────────


async def create_job(
    session: AsyncSession,
    *,
    type: str,
    payload: dict,
    queue_name: str = "default",
    priority: int = 0,
    max_attempts: int = 3,
    scheduled_at: datetime | None = None,
    idempotency_key: str | None = None,
    tenant_id: str | None = None,
    workflow_step_id: uuid.UUID | None = None,
) -> Job:
    now = _utcnow()
    available_at = scheduled_at if scheduled_at and scheduled_at > now else now

    job = Job(
        type=type,
        payload=payload,
        queue_name=queue_name,
        priority=priority,
        max_attempts=max_attempts,
        scheduled_at=scheduled_at,
        available_at=available_at,
        status=JobStatus.QUEUED,
        idempotency_key=idempotency_key,
        tenant_id=tenant_id,
        workflow_step_id=workflow_step_id,
    )
    session.add(job)
    await session.flush()

    await _emit_event(session, job.id, JobEventType.CREATED, "Job created")
    await session.commit()
    return job


# ────────────────────────── polling / leasing ──────────────────────────


async def poll_job(session: AsyncSession, worker_id: uuid.UUID, queues: list[str]) -> Job | None:
    """Atomically lease the highest-priority available job for the given worker."""
    now = _utcnow()
    lease_until = now + timedelta(seconds=settings.lease_duration_seconds)

    # Sub-query to find the best candidate
    subq = (
        select(Job.id)
        .where(
            Job.queue_name.in_(queues),
            Job.status == JobStatus.QUEUED,
            Job.available_at <= now,
        )
        .order_by(Job.priority.desc(), Job.available_at.asc())
        .limit(1)
        .with_for_update(skip_locked=True)
        .scalar_subquery()
    )

    result = await session.execute(
        update(Job)
        .where(Job.id == subq)
        .values(
            status=JobStatus.LEASED,
            worker_id=worker_id,
            lease_expires_at=lease_until,
            updated_at=now,
        )
        .returning(Job)
    )
    job = result.scalars().first()

    if job:
        await _emit_event(
            session,
            job.id,
            JobEventType.LEASED,
            f"Leased to worker {worker_id}",
            {"worker_id": str(worker_id), "lease_expires_at": lease_until.isoformat()},
        )
        await session.commit()
    return job


# ────────────────────────── start execution ──────────────────────────


async def start_job(session: AsyncSession, job_id: uuid.UUID, worker_id: uuid.UUID) -> Job | None:
    """Transition from LEASED → RUNNING. Called by worker after picking up."""
    now = _utcnow()
    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.LEASED, Job.worker_id == worker_id)
        .values(status=JobStatus.RUNNING, attempts=Job.attempts + 1, updated_at=now)
        .returning(Job)
    )
    job = result.scalars().first()
    if job:
        await _emit_event(session, job.id, JobEventType.RUNNING, f"Attempt {job.attempts}")
        await session.commit()
    return job


# ────────────────────────── completion ──────────────────────────


async def complete_job(
    session: AsyncSession, job_id: uuid.UUID, worker_id: uuid.UUID, result: dict | None = None
) -> Job | None:
    now = _utcnow()
    res = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.status == JobStatus.RUNNING, Job.worker_id == worker_id)
        .values(
            status=JobStatus.SUCCEEDED,
            lease_expires_at=None,
            worker_id=None,
            updated_at=now,
        )
        .returning(Job)
    )
    job = res.scalars().first()
    if job:
        await _emit_event(session, job.id, JobEventType.SUCCEEDED, "Job succeeded", result)
        await session.commit()
        from orchestrix.websocket import notify_job_update
        _fire_and_forget(notify_job_update(str(job.id), "SUCCEEDED"))
    return job


# ────────────────────────── failure ──────────────────────────


async def fail_job(
    session: AsyncSession, job_id: uuid.UUID, worker_id: uuid.UUID, error: str
) -> Job | None:
    """Handle job failure — retry with backoff OR dead-letter."""
    job = await session.get(Job, job_id)
    if not job or job.worker_id != worker_id or job.status != JobStatus.RUNNING:
        return None

    now = _utcnow()
    job.last_error = error
    job.lease_expires_at = None
    job.worker_id = None
    job.updated_at = now

    if job.attempts < job.max_attempts:
        # Use configurable retry policy per job type
        from orchestrix.engine.retry import get_retry_policy
        policy = get_retry_policy(job.type)
        delay = policy.compute_delay(job.attempts)
        job.available_at = now + timedelta(seconds=delay)
        job.status = JobStatus.QUEUED
        await _emit_event(
            session,
            job.id,
            JobEventType.RETRIED,
            f"Retrying ({policy.strategy.value}) after {delay:.1f}s (attempt {job.attempts}/{job.max_attempts})",
            {"delay_seconds": delay, "attempt": job.attempts, "strategy": policy.strategy.value},
        )
    else:
        job.status = JobStatus.DEAD_LETTER
        await _emit_event(
            session,
            job.id,
            JobEventType.DEAD_LETTERED,
            f"Exhausted {job.max_attempts} attempts — moved to dead letter",
        )

    await session.commit()
    from orchestrix.websocket import notify_job_update
    _fire_and_forget(notify_job_update(str(job.id), job.status.value))
    return job


# ────────────────────────── heartbeat ──────────────────────────


async def heartbeat_job(
    session: AsyncSession, job_id: uuid.UUID, worker_id: uuid.UUID
) -> Job | None:
    now = _utcnow()
    lease_until = now + timedelta(seconds=settings.lease_duration_seconds)

    result = await session.execute(
        update(Job)
        .where(Job.id == job_id, Job.worker_id == worker_id, Job.status == JobStatus.RUNNING)
        .values(lease_expires_at=lease_until, updated_at=now)
        .returning(Job)
    )
    job = result.scalars().first()
    if job:
        await _emit_event(session, job.id, JobEventType.HEARTBEAT, "Heartbeat received")
        await session.commit()
    return job


# ────────────────────────── stuck-job recovery ──────────────────────────


async def recover_stuck_jobs(session: AsyncSession) -> int:
    """Find jobs whose lease has expired and requeue them."""
    now = _utcnow()

    # Find stuck LEASED or RUNNING jobs with expired leases
    result = await session.execute(
        select(Job).where(
            Job.status.in_([JobStatus.LEASED, JobStatus.RUNNING]),
            Job.lease_expires_at < now,
        )
    )
    stuck_jobs = result.scalars().all()

    count = 0
    for job in stuck_jobs:
        job.updated_at = now
        job.lease_expires_at = None
        old_worker = job.worker_id
        job.worker_id = None

        if job.status == JobStatus.LEASED:
            # Never started — just requeue
            job.status = JobStatus.QUEUED
            job.available_at = now
            await _emit_event(
                session, job.id, JobEventType.REQUEUED,
                f"Lease expired (worker {old_worker} never started) — requeued",
            )
        elif job.status == JobStatus.RUNNING:
            # Was running — count as failure attempt
            job.attempts = min(job.attempts + 1, job.max_attempts) if job.attempts == 0 else job.attempts
            if job.attempts < job.max_attempts:
                delay = min(
                    settings.retry_base_delay_seconds * (2 ** (job.attempts - 1)),
                    settings.retry_max_delay_seconds,
                )
                job.available_at = now + timedelta(seconds=delay)
                job.status = JobStatus.QUEUED
                job.last_error = "Worker lost (lease expired)"
                await _emit_event(
                    session, job.id, JobEventType.RETRIED,
                    f"Worker {old_worker} lost — retrying after {delay:.1f}s",
                )
            else:
                job.status = JobStatus.DEAD_LETTER
                job.last_error = "Worker lost (lease expired)"
                await _emit_event(
                    session, job.id, JobEventType.DEAD_LETTERED,
                    f"Worker {old_worker} lost — exhausted attempts — dead-lettered",
                )
        count += 1

    if count:
        await session.commit()
    return count


# ────────────────────────── worker registration ──────────────────────────


async def register_worker(
    session: AsyncSession,
    name: str,
    queues: list[str],
    capabilities: list[str] | None = None,
    max_concurrency: int = 1,
) -> Worker:
    worker = Worker(
        name=name,
        queues=queues,
        capabilities=capabilities or [],
        max_concurrency=max_concurrency,
        status=WorkerStatus.ONLINE,
        last_heartbeat_at=_utcnow(),
    )
    session.add(worker)
    await session.commit()
    return worker


async def worker_heartbeat(session: AsyncSession, worker_id: uuid.UUID) -> Worker | None:
    worker = await session.get(Worker, worker_id)
    if not worker:
        return None
    worker.last_heartbeat_at = _utcnow()
    worker.status = WorkerStatus.ONLINE
    await session.commit()
    return worker


async def mark_stale_workers(session: AsyncSession) -> int:
    cutoff = _utcnow() - timedelta(seconds=settings.heartbeat_timeout_seconds)
    result = await session.execute(
        update(Worker)
        .where(Worker.status == WorkerStatus.ONLINE, Worker.last_heartbeat_at < cutoff)
        .values(status=WorkerStatus.OFFLINE)
    )
    await session.commit()
    return result.rowcount


# ────────────────────────── queries ──────────────────────────


async def get_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    return await session.get(Job, job_id)


async def list_jobs(
    session: AsyncSession,
    *,
    status: JobStatus | None = None,
    queue_name: str | None = None,
    tenant_id: str | None = None,
    worker_id: uuid.UUID | None = None,
    job_type: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[Job], int]:
    q = select(Job)
    count_q = select(func.count(Job.id))

    if status:
        q = q.where(Job.status == status)
        count_q = count_q.where(Job.status == status)
    if queue_name:
        q = q.where(Job.queue_name == queue_name)
        count_q = count_q.where(Job.queue_name == queue_name)
    if tenant_id:
        q = q.where(Job.tenant_id == tenant_id)
        count_q = count_q.where(Job.tenant_id == tenant_id)
    if worker_id:
        q = q.where(Job.worker_id == worker_id)
        count_q = count_q.where(Job.worker_id == worker_id)
    if job_type:
        q = q.where(Job.type == job_type)
        count_q = count_q.where(Job.type == job_type)

    q = q.order_by(Job.created_at.desc()).offset(offset).limit(limit)

    jobs = (await session.execute(q)).scalars().all()
    total = (await session.execute(count_q)).scalar()
    return list(jobs), total


async def get_job_events(session: AsyncSession, job_id: uuid.UUID) -> list[JobEvent]:
    result = await session.execute(
        select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.created_at.asc())
    )
    return list(result.scalars().all())


async def list_events(
    session: AsyncSession,
    *,
    since: datetime | None = None,
    event_type: JobEventType | None = None,
    limit: int = 100,
    offset: int = 0,
) -> tuple[list[JobEvent], int]:
    """List job events across all jobs, optionally filtered by time and type."""
    q = select(JobEvent)
    count_q = select(func.count(JobEvent.id))

    if since is not None:
        q = q.where(JobEvent.created_at >= since)
        count_q = count_q.where(JobEvent.created_at >= since)
    if event_type is not None:
        q = q.where(JobEvent.event_type == event_type)
        count_q = count_q.where(JobEvent.event_type == event_type)

    q = q.order_by(JobEvent.created_at.desc()).limit(limit).offset(offset)

    events = (await session.execute(q)).scalars().all()
    total = (await session.execute(count_q)).scalar()
    return list(events), total


async def list_workers(session: AsyncSession) -> list[Worker]:
    result = await session.execute(select(Worker).order_by(Worker.created_at.desc()))
    return list(result.scalars().all())


async def get_queue_stats(session: AsyncSession) -> list[dict]:
    result = await session.execute(
        select(
            Job.queue_name,
            func.count(case((Job.status == JobStatus.QUEUED, 1))).label("queued"),
            func.count(case((Job.status == JobStatus.LEASED, 1))).label("leased"),
            func.count(case((Job.status == JobStatus.RUNNING, 1))).label("running"),
            func.count(case((Job.status == JobStatus.SUCCEEDED, 1))).label("succeeded"),
            func.count(case((Job.status == JobStatus.FAILED, 1))).label("failed"),
            func.count(case((Job.status == JobStatus.DEAD_LETTER, 1))).label("dead_letter"),
        ).group_by(Job.queue_name)
    )
    return [
        {
            "queue_name": row.queue_name,
            "queued": row.queued,
            "leased": row.leased,
            "running": row.running,
            "succeeded": row.succeeded,
            "failed": row.failed,
            "dead_letter": row.dead_letter,
        }
        for row in result.all()
    ]


# ────────────────────────── operator actions ──────────────────────────


async def cancel_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    job = await session.get(Job, job_id)
    if not job or job.status not in (JobStatus.QUEUED, JobStatus.LEASED):
        return None
    job.status = JobStatus.CANCELLED
    job.lease_expires_at = None
    job.worker_id = None
    job.updated_at = _utcnow()
    await _emit_event(session, job.id, JobEventType.CANCELLED, "Cancelled by operator")
    await session.commit()
    return job


async def requeue_job(session: AsyncSession, job_id: uuid.UUID) -> Job | None:
    """Requeue a dead-lettered or failed job."""
    job = await session.get(Job, job_id)
    if not job or job.status not in (JobStatus.DEAD_LETTER, JobStatus.FAILED):
        return None
    now = _utcnow()
    job.status = JobStatus.QUEUED
    job.attempts = 0
    job.available_at = now
    job.lease_expires_at = None
    job.worker_id = None
    job.last_error = None
    job.updated_at = now
    await _emit_event(session, job.id, JobEventType.REQUEUED, "Requeued by operator")
    await session.commit()
    return job


# ────────────────────────── queue config ──────────────────────────


async def upsert_queue_config(
    session: AsyncSession,
    queue_name: str,
    max_concurrency: int | None = None,
    rate_limit_per_second: int | None = None,
) -> QueueConfig:
    existing = (
        await session.execute(select(QueueConfig).where(QueueConfig.queue_name == queue_name))
    ).scalars().first()

    if existing:
        if max_concurrency is not None:
            existing.max_concurrency = max_concurrency
        if rate_limit_per_second is not None:
            existing.rate_limit_per_second = rate_limit_per_second
        existing.updated_at = _utcnow()
    else:
        existing = QueueConfig(
            queue_name=queue_name,
            max_concurrency=max_concurrency,
            rate_limit_per_second=rate_limit_per_second,
        )
        session.add(existing)

    await session.commit()
    return existing


async def get_queue_config(session: AsyncSession, queue_name: str) -> QueueConfig | None:
    result = await session.execute(select(QueueConfig).where(QueueConfig.queue_name == queue_name))
    return result.scalars().first()


async def list_queue_configs(session: AsyncSession) -> list[QueueConfig]:
    result = await session.execute(select(QueueConfig).order_by(QueueConfig.queue_name))
    return list(result.scalars().all())


async def check_queue_concurrency(session: AsyncSession, queue_name: str) -> bool:
    """Return True if the queue has capacity (or no limit)."""
    config = await get_queue_config(session, queue_name)
    if not config or not config.max_concurrency:
        return True
    running = (
        await session.execute(
            select(func.count(Job.id)).where(
                Job.queue_name == queue_name,
                Job.status.in_([JobStatus.LEASED, JobStatus.RUNNING]),
            )
        )
    ).scalar()
    return running < config.max_concurrency


# ────────────────────────── recurring jobs ──────────────────────────


async def create_recurring_job(
    session: AsyncSession,
    *,
    name: str,
    type: str,
    payload: dict,
    cron_expression: str,
    queue_name: str = "default",
    max_attempts: int = 3,
    tenant_id: str | None = None,
) -> RecurringJob:
    from orchestrix.cron import next_cron_time

    now = _utcnow()
    next_run = next_cron_time(cron_expression, now)

    rj = RecurringJob(
        name=name,
        type=type,
        payload=payload,
        queue_name=queue_name,
        cron_expression=cron_expression,
        max_attempts=max_attempts,
        tenant_id=tenant_id,
        next_run_at=next_run,
    )
    session.add(rj)
    await session.commit()
    return rj


async def list_recurring_jobs(session: AsyncSession) -> list[RecurringJob]:
    result = await session.execute(select(RecurringJob).order_by(RecurringJob.name))
    return list(result.scalars().all())


async def get_recurring_job(session: AsyncSession, rj_id: uuid.UUID) -> RecurringJob | None:
    return await session.get(RecurringJob, rj_id)


async def toggle_recurring_job(session: AsyncSession, rj_id: uuid.UUID, enabled: bool) -> RecurringJob | None:
    rj = await session.get(RecurringJob, rj_id)
    if not rj:
        return None
    rj.enabled = enabled
    rj.updated_at = _utcnow()
    await session.commit()
    return rj


async def delete_recurring_job(session: AsyncSession, rj_id: uuid.UUID) -> bool:
    rj = await session.get(RecurringJob, rj_id)
    if not rj:
        return False
    await session.delete(rj)
    await session.commit()
    return True


async def tick_recurring_jobs(session: AsyncSession) -> int:
    """Check for recurring jobs due to fire and create job instances."""
    from orchestrix.cron import next_cron_time

    now = _utcnow()
    result = await session.execute(
        select(RecurringJob).where(
            RecurringJob.enabled == True,  # noqa: E712
            RecurringJob.next_run_at <= now,
        )
    )
    due_jobs = result.scalars().all()
    count = 0
    for rj in due_jobs:
        await create_job(
            session,
            type=rj.type,
            payload=rj.payload,
            queue_name=rj.queue_name,
            max_attempts=rj.max_attempts,
            tenant_id=rj.tenant_id,
        )
        rj.last_run_at = now
        rj.next_run_at = next_cron_time(rj.cron_expression, now)
        rj.updated_at = now
        count += 1

    if count:
        await session.commit()
    return count
