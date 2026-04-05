import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.database import get_session
from orchestrix.engine import core
from orchestrix.models.enums import JobStatus
from orchestrix.schemas import (
    JobCreate,
    JobEventResponse,
    JobListResponse,
    JobResponse,
    QueueConfigCreate,
    QueueConfigResponse,
    QueueStats,
    RecurringJobCreate,
    RecurringJobResponse,
    RecurringJobToggle,
)

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.post("", response_model=JobResponse, status_code=201)
async def create_job(body: JobCreate, session: AsyncSession = Depends(get_session)):
    job = await core.create_job(
        session,
        type=body.type,
        payload=body.payload,
        queue_name=body.queue_name,
        priority=body.priority,
        max_attempts=body.max_attempts,
        scheduled_at=body.scheduled_at,
        idempotency_key=body.idempotency_key,
        tenant_id=body.tenant_id,
    )
    return job


@router.get("", response_model=JobListResponse)
async def list_jobs(
    status: JobStatus | None = Query(None),
    queue_name: str | None = Query(None),
    tenant_id: str | None = Query(None),
    worker_id: uuid.UUID | None = Query(None),
    job_type: str | None = Query(None, alias="type"),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    jobs, total = await core.list_jobs(
        session,
        status=status,
        queue_name=queue_name,
        tenant_id=tenant_id,
        worker_id=worker_id,
        job_type=job_type,
        limit=limit,
        offset=offset,
    )
    return JobListResponse(
        jobs=[JobResponse.model_validate(j) for j in jobs], total=total
    )


@router.get("/stats", response_model=list[QueueStats])
async def queue_stats(session: AsyncSession = Depends(get_session)):
    rows = await core.get_queue_stats(session)
    return [QueueStats(**r) for r in rows]


@router.get("/{job_id}", response_model=JobResponse)
async def get_job(job_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    job = await core.get_job(session, job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


@router.get("/{job_id}/events", response_model=list[JobEventResponse])
async def get_job_events(
    job_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    events = await core.get_job_events(session, job_id)
    return [JobEventResponse.model_validate(e) for e in events]


@router.post("/{job_id}/cancel", response_model=JobResponse)
async def cancel_job(job_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    job = await core.cancel_job(session, job_id)
    if not job:
        raise HTTPException(
            status_code=409, detail="Job cannot be cancelled in its current state"
        )
    return job


@router.post("/{job_id}/requeue", response_model=JobResponse)
async def requeue_job(job_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    job = await core.requeue_job(session, job_id)
    if not job:
        raise HTTPException(
            status_code=409, detail="Job cannot be requeued in its current state"
        )
    return job


# ── Queue Config ──

queue_router = APIRouter(prefix="/queues", tags=["queues"])


@queue_router.get("", response_model=list[QueueConfigResponse])
async def list_queue_configs(session: AsyncSession = Depends(get_session)):
    configs = await core.list_queue_configs(session)
    return [QueueConfigResponse.model_validate(c) for c in configs]


@queue_router.put("/{queue_name}", response_model=QueueConfigResponse)
async def upsert_queue_config(
    queue_name: str,
    body: QueueConfigCreate,
    session: AsyncSession = Depends(get_session),
):
    config = await core.upsert_queue_config(
        session,
        queue_name=queue_name,
        max_concurrency=body.max_concurrency,
        rate_limit_per_second=body.rate_limit_per_second,
    )
    return QueueConfigResponse.model_validate(config)


# ── Recurring Jobs ──

recurring_router = APIRouter(prefix="/recurring", tags=["recurring"])


@recurring_router.post("", response_model=RecurringJobResponse, status_code=201)
async def create_recurring_job(
    body: RecurringJobCreate, session: AsyncSession = Depends(get_session)
):
    rj = await core.create_recurring_job(
        session,
        name=body.name,
        type=body.type,
        payload=body.payload,
        cron_expression=body.cron_expression,
        queue_name=body.queue_name,
        max_attempts=body.max_attempts,
        tenant_id=body.tenant_id,
    )
    return rj


@recurring_router.get("", response_model=list[RecurringJobResponse])
async def list_recurring_jobs(session: AsyncSession = Depends(get_session)):
    jobs = await core.list_recurring_jobs(session)
    return [RecurringJobResponse.model_validate(j) for j in jobs]


@recurring_router.get("/{rj_id}", response_model=RecurringJobResponse)
async def get_recurring_job(
    rj_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    rj = await core.get_recurring_job(session, rj_id)
    if not rj:
        raise HTTPException(status_code=404, detail="Recurring job not found")
    return rj


@recurring_router.patch("/{rj_id}", response_model=RecurringJobResponse)
async def toggle_recurring_job(
    rj_id: uuid.UUID,
    body: RecurringJobToggle,
    session: AsyncSession = Depends(get_session),
):
    rj = await core.toggle_recurring_job(session, rj_id, body.enabled)
    if not rj:
        raise HTTPException(status_code=404, detail="Recurring job not found")
    return rj


@recurring_router.delete("/{rj_id}", status_code=204)
async def delete_recurring_job(
    rj_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    deleted = await core.delete_recurring_job(session, rj_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Recurring job not found")
