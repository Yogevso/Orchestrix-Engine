import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.database import get_session
from orchestrix.engine import core
from orchestrix.models.tables import Worker
from orchestrix.schemas import (
    CompleteRequest,
    FailRequest,
    HeartbeatRequest,
    JobResponse,
    PollResponse,
    WorkerRegister,
    WorkerResponse,
)

router = APIRouter(prefix="/workers", tags=["workers"])


@router.post("", response_model=WorkerResponse, status_code=201)
async def register_worker(body: WorkerRegister, session: AsyncSession = Depends(get_session)):
    worker = await core.register_worker(
        session,
        name=body.name,
        queues=body.queues,
        capabilities=body.capabilities,
        max_concurrency=body.max_concurrency,
    )
    return worker


@router.get("", response_model=list[WorkerResponse])
async def list_workers(session: AsyncSession = Depends(get_session)):
    workers = await core.list_workers(session)
    return [WorkerResponse.model_validate(w) for w in workers]


@router.post("/{worker_id}/poll", response_model=PollResponse)
async def poll_job(worker_id: uuid.UUID, session: AsyncSession = Depends(get_session)):
    worker = await session.get(Worker, worker_id)
    if not worker:
        raise HTTPException(status_code=404, detail="Worker not found")

    job = await core.poll_job(session, worker_id, worker.queues)
    if not job:
        return PollResponse(job=None, lease_expires_at=None)

    return PollResponse(
        job=JobResponse.model_validate(job),
        lease_expires_at=job.lease_expires_at,
    )


@router.post("/{worker_id}/start", response_model=JobResponse)
async def start_job(worker_id: uuid.UUID, body: HeartbeatRequest, session: AsyncSession = Depends(get_session)):
    job = await core.start_job(session, body.job_id, worker_id)
    if not job:
        raise HTTPException(status_code=409, detail="Cannot start job")
    return JobResponse.model_validate(job)


@router.post("/{worker_id}/complete", response_model=JobResponse)
async def complete_job(worker_id: uuid.UUID, body: CompleteRequest, session: AsyncSession = Depends(get_session)):
    job = await core.complete_job(session, body.job_id, worker_id, body.result)
    if not job:
        raise HTTPException(status_code=409, detail="Cannot complete job")
    return job


@router.post("/{worker_id}/fail", response_model=JobResponse)
async def fail_job(worker_id: uuid.UUID, body: FailRequest, session: AsyncSession = Depends(get_session)):
    job = await core.fail_job(session, body.job_id, worker_id, body.error)
    if not job:
        raise HTTPException(status_code=409, detail="Cannot fail job")
    return job


@router.post("/{worker_id}/heartbeat")
async def heartbeat(worker_id: uuid.UUID, body: HeartbeatRequest, session: AsyncSession = Depends(get_session)):
    # Heartbeat on the worker itself
    await core.worker_heartbeat(session, worker_id)
    # Heartbeat on the job lease
    job = await core.heartbeat_job(session, body.job_id, worker_id)
    if not job:
        raise HTTPException(status_code=409, detail="Cannot heartbeat job")
    return {"status": "ok", "lease_expires_at": job.lease_expires_at.isoformat()}
