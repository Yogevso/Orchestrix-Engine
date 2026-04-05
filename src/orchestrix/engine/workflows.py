"""Workflow engine — DAG execution, fan-out/fan-in, step-level retries."""

import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.engine import core
from orchestrix.models.enums import (
    JobStatus,
    WorkflowStatus,
    WorkflowStepStatus,
)
from orchestrix.models.tables import Job, Workflow, WorkflowRun, WorkflowStep


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ────────────────────────── workflow CRUD ──────────────────────────


async def create_workflow(
    session: AsyncSession,
    *,
    name: str,
    description: str | None,
    steps: list[dict],
    tenant_id: str | None = None,
) -> Workflow:
    """Create a workflow definition.

    `steps` is a list of dicts with keys: name, job_type, payload, depends_on, max_attempts.
    """
    # Validate DAG: check no missing dependencies and no cycles
    step_names = {s["name"] for s in steps}
    for s in steps:
        for dep in s.get("depends_on", []):
            if dep not in step_names:
                raise ValueError(f"Step '{s['name']}' depends on unknown step '{dep}'")

    _detect_cycle(steps)

    definition = {"steps": steps}
    wf = Workflow(
        name=name,
        description=description,
        definition=definition,
        tenant_id=tenant_id,
    )
    session.add(wf)
    await session.commit()
    return wf


def _detect_cycle(steps: list[dict]) -> None:
    """Detect cycles in the step dependency graph using DFS."""
    adj: dict[str, list[str]] = {s["name"]: s.get("depends_on", []) for s in steps}
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {name: WHITE for name in adj}

    def dfs(node: str) -> None:
        color[node] = GRAY
        for dep in adj[node]:
            if color[dep] == GRAY:
                raise ValueError(f"Cycle detected involving step '{dep}'")
            if color[dep] == WHITE:
                dfs(dep)
        color[node] = BLACK

    for name in adj:
        if color[name] == WHITE:
            dfs(name)


async def get_workflow(session: AsyncSession, workflow_id: uuid.UUID) -> Workflow | None:
    return await session.get(Workflow, workflow_id)


async def list_workflows(session: AsyncSession) -> list[Workflow]:
    result = await session.execute(select(Workflow).order_by(Workflow.created_at.desc()))
    return list(result.scalars().all())


# ────────────────────────── workflow runs ──────────────────────────


async def start_workflow_run(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID,
    input_payload: dict,
    tenant_id: str | None = None,
) -> WorkflowRun:
    """Create a workflow run and instantiate all steps from the definition."""
    wf = await session.get(Workflow, workflow_id)
    if not wf:
        raise ValueError("Workflow not found")

    now = _utcnow()
    run = WorkflowRun(
        workflow_id=workflow_id,
        status=WorkflowStatus.RUNNING,
        input_payload=input_payload,
        tenant_id=tenant_id or wf.tenant_id,
        started_at=now,
    )
    session.add(run)
    await session.flush()

    # Create step instances
    for step_def in wf.definition["steps"]:
        step = WorkflowStep(
            workflow_run_id=run.id,
            step_name=step_def["name"],
            job_type=step_def["job_type"],
            payload=step_def.get("payload", {}),
            depends_on=step_def.get("depends_on", []),
            max_attempts=step_def.get("max_attempts", 3),
            status=WorkflowStepStatus.PENDING,
        )
        session.add(step)

    await session.commit()

    # Immediately try to advance (dispatch ready steps)
    await _advance_run(session, run.id)

    return run


async def get_workflow_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    return await session.get(WorkflowRun, run_id)


async def get_run_steps(session: AsyncSession, run_id: uuid.UUID) -> list[WorkflowStep]:
    result = await session.execute(
        select(WorkflowStep)
        .where(WorkflowStep.workflow_run_id == run_id)
        .order_by(WorkflowStep.created_at.asc())
    )
    return list(result.scalars().all())


async def list_workflow_runs(
    session: AsyncSession,
    *,
    workflow_id: uuid.UUID | None = None,
    status: WorkflowStatus | None = None,
    tenant_id: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> list[WorkflowRun]:
    q = select(WorkflowRun)
    if workflow_id:
        q = q.where(WorkflowRun.workflow_id == workflow_id)
    if status:
        q = q.where(WorkflowRun.status == status)
    if tenant_id:
        q = q.where(WorkflowRun.tenant_id == tenant_id)
    q = q.order_by(WorkflowRun.created_at.desc()).offset(offset).limit(limit)
    result = await session.execute(q)
    return list(result.scalars().all())


# ────────────────────────── step advancement (DAG core) ──────────────────────────


async def _advance_run(session: AsyncSession, run_id: uuid.UUID) -> int:
    """Find PENDING steps whose dependencies are met and dispatch them as jobs.

    Returns the number of steps dispatched.
    """
    # Don't dispatch new steps if the run is paused
    run = await session.get(WorkflowRun, run_id)
    if run and run.status == WorkflowStatus.PAUSED:
        return 0

    steps = await get_run_steps(session, run_id)
    step_map = {s.step_name: s for s in steps}
    dispatched = 0

    for step in steps:
        if step.status != WorkflowStepStatus.PENDING:
            continue

        # Check all dependencies are SUCCEEDED
        deps_met = all(
            step_map[dep].status == WorkflowStepStatus.SUCCEEDED
            for dep in step.depends_on
            if dep in step_map
        )
        if not deps_met:
            continue

        # Merge parent outputs into payload for fan-in
        merged_payload = dict(step.payload)
        parent_results = {}
        for dep_name in step.depends_on:
            dep_step = step_map.get(dep_name)
            if dep_step and dep_step.result:
                parent_results[dep_name] = dep_step.result
        if parent_results:
            merged_payload["_parent_results"] = parent_results

        # Dispatch: create a real job linked to this step
        run = await session.get(WorkflowRun, run_id)
        job = await core.create_job(
            session,
            type=step.job_type,
            payload=merged_payload,
            queue_name="default",
            max_attempts=step.max_attempts,
            tenant_id=run.tenant_id if run else None,
            workflow_step_id=step.id,
        )
        step.status = WorkflowStepStatus.QUEUED
        step.job_id = job.id
        step.started_at = _utcnow()
        dispatched += 1

    if dispatched:
        await session.commit()

    return dispatched


async def on_job_completed(session: AsyncSession, job: Job) -> None:
    """Called when a job tied to a workflow step completes successfully."""
    if not job.workflow_step_id:
        return

    step = await session.get(WorkflowStep, job.workflow_step_id)
    if not step:
        return

    now = _utcnow()
    step.status = WorkflowStepStatus.SUCCEEDED
    step.finished_at = now
    # Store the job event result if available
    step.result = {}  # Will be populated with completion data
    step.attempts += 1
    await session.commit()

    # Try to advance the run
    await _advance_run(session, step.workflow_run_id)

    # Check if the entire run is done
    await _check_run_completion(session, step.workflow_run_id)


async def on_job_failed(session: AsyncSession, job: Job) -> None:
    """Called when a job tied to a workflow step fails (after all retries exhausted)."""
    if not job.workflow_step_id:
        return

    step = await session.get(WorkflowStep, job.workflow_step_id)
    if not step:
        return

    now = _utcnow()

    if job.status == JobStatus.DEAD_LETTER:
        # Step truly failed
        step.status = WorkflowStepStatus.FAILED
        step.last_error = job.last_error
        step.finished_at = now
        step.attempts = job.attempts
        await session.commit()

        # Mark the whole run as failed
        run = await session.get(WorkflowRun, step.workflow_run_id)
        if run and run.status == WorkflowStatus.RUNNING:
            run.status = WorkflowStatus.FAILED
            run.finished_at = now
            # Cancel any pending/queued steps
            pending_steps = await session.execute(
                select(WorkflowStep).where(
                    WorkflowStep.workflow_run_id == step.workflow_run_id,
                    WorkflowStep.status.in_([
                        WorkflowStepStatus.PENDING,
                        WorkflowStepStatus.QUEUED,
                    ]),
                )
            )
            for ps in pending_steps.scalars().all():
                ps.status = WorkflowStepStatus.CANCELLED
            await session.commit()


async def _check_run_completion(session: AsyncSession, run_id: uuid.UUID) -> None:
    """Check if all steps in a run are done and update run status."""
    steps = await get_run_steps(session, run_id)
    all_done = all(
        s.status in (WorkflowStepStatus.SUCCEEDED, WorkflowStepStatus.SKIPPED)
        for s in steps
    )
    any_failed = any(s.status == WorkflowStepStatus.FAILED for s in steps)

    run = await session.get(WorkflowRun, run_id)
    if not run or run.status != WorkflowStatus.RUNNING:
        return

    now = _utcnow()
    if any_failed:
        run.status = WorkflowStatus.FAILED
        run.finished_at = now
        await session.commit()
    elif all_done:
        # Collect outputs from leaf steps (steps no one depends on)
        dep_targets = set()
        for s in steps:
            dep_targets.update(s.depends_on)
        leaf_steps = [s for s in steps if s.step_name not in dep_targets]

        run.output = {s.step_name: s.result for s in leaf_steps if s.result}
        run.status = WorkflowStatus.SUCCEEDED
        run.finished_at = now
        await session.commit()


# ────────────────────────── operator actions ──────────────────────────


async def cancel_workflow_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    run = await session.get(WorkflowRun, run_id)
    if not run or run.status not in (WorkflowStatus.PENDING, WorkflowStatus.RUNNING):
        return None

    now = _utcnow()
    run.status = WorkflowStatus.CANCELLED
    run.finished_at = now

    # Cancel all non-completed steps
    steps_result = await session.execute(
        select(WorkflowStep).where(
            WorkflowStep.workflow_run_id == run_id,
            WorkflowStep.status.in_([
                WorkflowStepStatus.PENDING,
                WorkflowStepStatus.QUEUED,
                WorkflowStepStatus.RUNNING,
            ]),
        )
    )
    for step in steps_result.scalars().all():
        step.status = WorkflowStepStatus.CANCELLED
        # Cancel the associated job if exists
        if step.job_id:
            await core.cancel_job(session, step.job_id)

    await session.commit()
    return run


async def pause_workflow_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    """Pause a running workflow — no new steps will be dispatched."""
    run = await session.get(WorkflowRun, run_id)
    if not run or run.status != WorkflowStatus.RUNNING:
        return None

    run.status = WorkflowStatus.PAUSED
    run.updated_at = _utcnow()
    await session.commit()
    return run


async def resume_workflow_run(session: AsyncSession, run_id: uuid.UUID) -> WorkflowRun | None:
    """Resume a paused workflow — re-dispatches ready steps."""
    run = await session.get(WorkflowRun, run_id)
    if not run or run.status != WorkflowStatus.PAUSED:
        return None

    run.status = WorkflowStatus.RUNNING
    run.updated_at = _utcnow()
    await session.commit()

    # Advance any steps that became ready while paused
    await _advance_run(session, run.id)
    return run


async def retry_workflow_step(session: AsyncSession, step_id: uuid.UUID) -> WorkflowStep | None:
    """Retry a specific failed workflow step."""
    step = await session.get(WorkflowStep, step_id)
    if not step or step.status != WorkflowStepStatus.FAILED:
        return None

    # Re-dispatch
    run = await session.get(WorkflowRun, step.workflow_run_id)
    if not run:
        return None

    # Reset run to running if it was failed
    if run.status == WorkflowStatus.FAILED:
        run.status = WorkflowStatus.RUNNING
        run.finished_at = None

    step.status = WorkflowStepStatus.PENDING
    step.last_error = None
    step.result = None
    step.job_id = None
    step.finished_at = None
    await session.commit()

    # Advance to re-dispatch
    await _advance_run(session, step.workflow_run_id)
    return step


# ────────────────────────── scheduler hook ──────────────────────────


async def advance_all_pending_runs(session: AsyncSession) -> int:
    """Called by the scheduler to sync workflow step statuses with job statuses."""
    # Find RUNNING workflow steps with completed jobs
    result = await session.execute(
        select(WorkflowStep).where(
            WorkflowStep.status == WorkflowStepStatus.QUEUED,
            WorkflowStep.job_id.isnot(None),
        )
    )
    steps = result.scalars().all()
    advanced = 0

    for step in steps:
        job = await session.get(Job, step.job_id)
        if not job:
            continue

        if job.status == JobStatus.SUCCEEDED:
            step.status = WorkflowStepStatus.SUCCEEDED
            step.finished_at = _utcnow()
            step.attempts = job.attempts
            await session.commit()
            await _advance_run(session, step.workflow_run_id)
            await _check_run_completion(session, step.workflow_run_id)
            advanced += 1

        elif job.status == JobStatus.DEAD_LETTER:
            await on_job_failed(session, job)
            advanced += 1

        elif job.status == JobStatus.RUNNING:
            step.status = WorkflowStepStatus.RUNNING
            await session.commit()

    return advanced
