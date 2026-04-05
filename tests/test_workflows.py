"""Unit tests for the workflow engine — DAG creation, cycle detection, advancement."""

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.engine import workflows
from orchestrix.models.enums import WorkflowStatus, WorkflowStepStatus


pytestmark = pytest.mark.asyncio


# ── Workflow creation ──


async def test_create_workflow(session: AsyncSession):
    wf = await workflows.create_workflow(
        session,
        name="test-wf",
        description="A test workflow",
        steps=[
            {
                "name": "step1",
                "job_type": "email.send",
                "payload": {},
                "depends_on": [],
                "max_attempts": 3,
            },
            {
                "name": "step2",
                "job_type": "data.process",
                "payload": {},
                "depends_on": ["step1"],
                "max_attempts": 3,
            },
        ],
    )
    assert wf.id is not None
    assert wf.name == "test-wf"
    assert len(wf.definition["steps"]) == 2


async def test_cycle_detection(session: AsyncSession):
    with pytest.raises(ValueError, match="Cycle detected"):
        await workflows.create_workflow(
            session,
            name="cyclic-wf",
            description=None,
            steps=[
                {
                    "name": "a",
                    "job_type": "email.send",
                    "payload": {},
                    "depends_on": ["b"],
                },
                {
                    "name": "b",
                    "job_type": "email.send",
                    "payload": {},
                    "depends_on": ["a"],
                },
            ],
        )


async def test_missing_dependency_detection(session: AsyncSession):
    with pytest.raises(ValueError, match="unknown step"):
        await workflows.create_workflow(
            session,
            name="bad-dep-wf",
            description=None,
            steps=[
                {
                    "name": "a",
                    "job_type": "email.send",
                    "payload": {},
                    "depends_on": ["nonexistent"],
                },
            ],
        )


# ── Workflow run ──


async def test_start_workflow_run(session: AsyncSession):
    wf = await workflows.create_workflow(
        session,
        name="run-test-wf",
        description=None,
        steps=[
            {
                "name": "root",
                "job_type": "email.send",
                "payload": {},
                "depends_on": [],
                "max_attempts": 3,
            },
        ],
    )
    run = await workflows.start_workflow_run(
        session, workflow_id=wf.id, input_payload={"x": 1}
    )
    assert run.status == WorkflowStatus.RUNNING
    steps = await workflows.get_run_steps(session, run.id)
    assert len(steps) == 1
    # Root step should be dispatched immediately (QUEUED, not PENDING)
    assert steps[0].status == WorkflowStepStatus.QUEUED


async def test_cancel_workflow_run(session: AsyncSession):
    wf = await workflows.create_workflow(
        session,
        name="cancel-wf",
        description=None,
        steps=[
            {
                "name": "s1",
                "job_type": "email.send",
                "payload": {},
                "depends_on": [],
                "max_attempts": 3,
            },
        ],
    )
    run = await workflows.start_workflow_run(
        session, workflow_id=wf.id, input_payload={}
    )
    cancelled = await workflows.cancel_workflow_run(session, run.id)
    assert cancelled is not None
    assert cancelled.status == WorkflowStatus.CANCELLED


# ── List workflows ──


async def test_list_workflows(session: AsyncSession):
    await workflows.create_workflow(
        session,
        name="list-wf-1",
        description=None,
        steps=[
            {"name": "s", "job_type": "email.send", "payload": {}, "depends_on": []}
        ],
    )
    wfs = await workflows.list_workflows(session)
    names = [w.name for w in wfs]
    assert "list-wf-1" in names
