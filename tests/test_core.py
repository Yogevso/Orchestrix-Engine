"""Unit tests for the core engine — job lifecycle, retries, dead-lettering."""

import uuid

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.engine import core
from orchestrix.models.enums import JobEventType, JobStatus, WorkerStatus


pytestmark = pytest.mark.asyncio


# ── Job creation ──


async def test_create_job(session: AsyncSession):
    job = await core.create_job(session, type="email.send", payload={"to": "a@b.com"})
    assert job.id is not None
    assert job.type == "email.send"
    assert job.status == JobStatus.QUEUED
    assert job.attempts == 0
    assert job.queue_name == "default"


async def test_create_job_custom_queue(session: AsyncSession):
    job = await core.create_job(session, type="data.process", payload={}, queue_name="high")
    assert job.queue_name == "high"


async def test_create_job_with_priority(session: AsyncSession):
    job = await core.create_job(session, type="report.generate", payload={}, priority=10)
    assert job.priority == 10


# ── Polling / leasing ──


async def test_poll_job_returns_job(session: AsyncSession):
    worker = await core.register_worker(session, name="w1", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={})
    polled = await core.poll_job(session, worker.id, ["default"])
    assert polled is not None
    assert polled.id == job.id
    assert polled.status == JobStatus.LEASED
    assert polled.worker_id == worker.id


async def test_poll_job_empty_queue(session: AsyncSession):
    worker = await core.register_worker(session, name="w2", queues=["empty-queue"])
    polled = await core.poll_job(session, worker.id, ["empty-queue"])
    assert polled is None


async def test_poll_job_respects_queue(session: AsyncSession):
    worker = await core.register_worker(session, name="w3", queues=["other"])
    await core.create_job(session, type="email.send", payload={}, queue_name="default")
    polled = await core.poll_job(session, worker.id, ["other"])
    assert polled is None


# ── Start job ──


async def test_start_job(session: AsyncSession):
    worker = await core.register_worker(session, name="w4", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={})
    polled = await core.poll_job(session, worker.id, ["default"])
    started = await core.start_job(session, polled.id, worker.id)
    assert started is not None
    assert started.status == JobStatus.RUNNING
    assert started.attempts == 1


# ── Complete job ──


async def test_complete_job(session: AsyncSession):
    worker = await core.register_worker(session, name="w5", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={})
    polled = await core.poll_job(session, worker.id, ["default"])
    started = await core.start_job(session, polled.id, worker.id)
    completed = await core.complete_job(session, started.id, worker.id, {"sent": True})
    assert completed is not None
    assert completed.status == JobStatus.SUCCEEDED


# ── Fail job with retries ──


async def test_fail_job_retries(session: AsyncSession):
    worker = await core.register_worker(session, name="w6", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={}, max_attempts=3)
    polled = await core.poll_job(session, worker.id, ["default"])
    started = await core.start_job(session, polled.id, worker.id)
    failed = await core.fail_job(session, started.id, worker.id, "connection timeout")
    assert failed is not None
    assert failed.status == JobStatus.QUEUED  # Retried
    assert failed.last_error == "connection timeout"


async def test_fail_job_dead_letter(session: AsyncSession):
    worker = await core.register_worker(session, name="w7", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={}, max_attempts=1)
    polled = await core.poll_job(session, worker.id, ["default"])
    started = await core.start_job(session, polled.id, worker.id)
    failed = await core.fail_job(session, started.id, worker.id, "crash")
    assert failed is not None
    assert failed.status == JobStatus.DEAD_LETTER


# ── Cancel / requeue ──


async def test_cancel_queued_job(session: AsyncSession):
    job = await core.create_job(session, type="email.send", payload={})
    cancelled = await core.cancel_job(session, job.id)
    assert cancelled is not None
    assert cancelled.status == JobStatus.CANCELLED


async def test_requeue_dead_letter_job(session: AsyncSession):
    worker = await core.register_worker(session, name="w8", queues=["default"])
    job = await core.create_job(session, type="email.send", payload={}, max_attempts=1)
    polled = await core.poll_job(session, worker.id, ["default"])
    started = await core.start_job(session, polled.id, worker.id)
    await core.fail_job(session, started.id, worker.id, "crash")
    requeued = await core.requeue_job(session, job.id)
    assert requeued is not None
    assert requeued.status == JobStatus.QUEUED
    assert requeued.attempts == 0


# ── Worker registration ──


async def test_register_worker(session: AsyncSession):
    worker = await core.register_worker(session, name="test-worker", queues=["alpha", "beta"])
    assert worker.id is not None
    assert worker.name == "test-worker"
    assert worker.queues == ["alpha", "beta"]
    assert worker.status == WorkerStatus.ONLINE


async def test_list_workers(session: AsyncSession):
    await core.register_worker(session, name="list-w1", queues=["default"])
    await core.register_worker(session, name="list-w2", queues=["default"])
    workers = await core.list_workers(session)
    names = [w.name for w in workers]
    assert "list-w1" in names
    assert "list-w2" in names


# ── Job events ──


async def test_job_events_created(session: AsyncSession):
    job = await core.create_job(session, type="email.send", payload={})
    events = await core.get_job_events(session, job.id)
    assert len(events) >= 1
    assert events[0].event_type == JobEventType.CREATED


# ── Queue stats ──


async def test_queue_stats(session: AsyncSession):
    await core.create_job(session, type="email.send", payload={}, queue_name="stats-q")
    stats = await core.get_queue_stats(session)
    match = [s for s in stats if s["queue_name"] == "stats-q"]
    assert len(match) == 1
    assert match[0]["queued"] >= 1
