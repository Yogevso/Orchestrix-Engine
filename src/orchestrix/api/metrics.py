"""Prometheus-compatible metrics endpoint."""

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.database import get_session
from orchestrix.models.tables import Job, Worker, WorkflowRun

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def metrics(session: AsyncSession = Depends(get_session)):
    lines: list[str] = []

    # ── Job counts by status ──
    result = await session.execute(
        select(Job.status, func.count(Job.id)).group_by(Job.status)
    )
    lines.append("# HELP orchestrix_jobs_total Total jobs by status")
    lines.append("# TYPE orchestrix_jobs_total gauge")
    for status, count in result.all():
        lines.append(f'orchestrix_jobs_total{{status="{status.value}"}} {count}')

    # ── Job counts by queue ──
    result = await session.execute(
        select(Job.queue_name, Job.status, func.count(Job.id)).group_by(
            Job.queue_name, Job.status
        )
    )
    lines.append("# HELP orchestrix_queue_jobs Jobs per queue by status")
    lines.append("# TYPE orchestrix_queue_jobs gauge")
    for queue, status, count in result.all():
        lines.append(
            f'orchestrix_queue_jobs{{queue="{queue}",status="{status.value}"}} {count}'
        )

    # ── Workers by status ──
    result = await session.execute(
        select(Worker.status, func.count(Worker.id)).group_by(Worker.status)
    )
    lines.append("# HELP orchestrix_workers_total Workers by status")
    lines.append("# TYPE orchestrix_workers_total gauge")
    for status, count in result.all():
        lines.append(f'orchestrix_workers_total{{status="{status.value}"}} {count}')

    # ── Workflow runs by status ──
    result = await session.execute(
        select(WorkflowRun.status, func.count(WorkflowRun.id)).group_by(
            WorkflowRun.status
        )
    )
    lines.append("# HELP orchestrix_workflow_runs_total Workflow runs by status")
    lines.append("# TYPE orchestrix_workflow_runs_total gauge")
    for status, count in result.all():
        lines.append(
            f'orchestrix_workflow_runs_total{{status="{status.value}"}} {count}'
        )

    return "\n".join(lines) + "\n"
