import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from orchestrix.database import get_session
from orchestrix.engine import workflows
from orchestrix.models.enums import WorkflowStatus
from orchestrix.schemas import (
    WorkflowCreate,
    WorkflowResponse,
    WorkflowRunCreate,
    WorkflowRunResponse,
    WorkflowStepResponse,
)

router = APIRouter(prefix="/workflows", tags=["workflows"])


# ── Workflow definitions ──


@router.post("", response_model=WorkflowResponse, status_code=201)
async def create_workflow(
    body: WorkflowCreate, session: AsyncSession = Depends(get_session)
):
    try:
        wf = await workflows.create_workflow(
            session,
            name=body.name,
            description=body.description,
            steps=[s.model_dump() for s in body.steps],
            tenant_id=body.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return wf


@router.get("", response_model=list[WorkflowResponse])
async def list_workflows(session: AsyncSession = Depends(get_session)):
    wfs = await workflows.list_workflows(session)
    return [WorkflowResponse.model_validate(w) for w in wfs]


# ── Workflow runs (must be before /{workflow_id} to avoid route conflict) ──


@router.post("/runs", response_model=WorkflowRunResponse, status_code=201)
async def start_workflow_run(
    body: WorkflowRunCreate, session: AsyncSession = Depends(get_session)
):
    try:
        run = await workflows.start_workflow_run(
            session,
            workflow_id=body.workflow_id,
            input_payload=body.input_payload,
            tenant_id=body.tenant_id,
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    steps = await workflows.get_run_steps(session, run.id)
    return WorkflowRunResponse(
        **{
            k: v
            for k, v in WorkflowRunResponse.model_validate(run).model_dump().items()
            if k != "steps"
        },
        steps=[WorkflowStepResponse.model_validate(s) for s in steps],
    )


@router.get("/runs", response_model=list[WorkflowRunResponse])
async def list_workflow_runs(
    workflow_id: uuid.UUID | None = Query(None),
    status: WorkflowStatus | None = Query(None),
    tenant_id: str | None = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    runs = await workflows.list_workflow_runs(
        session,
        workflow_id=workflow_id,
        status=status,
        tenant_id=tenant_id,
        limit=limit,
        offset=offset,
    )
    results = []
    for run in runs:
        steps = await workflows.get_run_steps(session, run.id)
        resp = WorkflowRunResponse.model_validate(run)
        resp.steps = [WorkflowStepResponse.model_validate(s) for s in steps]
        results.append(resp)
    return results


@router.get("/runs/{run_id}", response_model=WorkflowRunResponse)
async def get_workflow_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    run = await workflows.get_workflow_run(session, run_id)
    if not run:
        raise HTTPException(status_code=404, detail="Workflow run not found")

    steps = await workflows.get_run_steps(session, run.id)
    resp = WorkflowRunResponse.model_validate(run)
    resp.steps = [WorkflowStepResponse.model_validate(s) for s in steps]
    return resp


@router.post("/runs/{run_id}/cancel", response_model=WorkflowRunResponse)
async def cancel_workflow_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    run = await workflows.cancel_workflow_run(session, run_id)
    if not run:
        raise HTTPException(status_code=409, detail="Cannot cancel this workflow run")

    steps = await workflows.get_run_steps(session, run.id)
    resp = WorkflowRunResponse.model_validate(run)
    resp.steps = [WorkflowStepResponse.model_validate(s) for s in steps]
    return resp


@router.post("/runs/{run_id}/pause", response_model=WorkflowRunResponse)
async def pause_workflow_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    run = await workflows.pause_workflow_run(session, run_id)
    if not run:
        raise HTTPException(
            status_code=409, detail="Cannot pause this workflow run (must be RUNNING)"
        )

    steps = await workflows.get_run_steps(session, run.id)
    resp = WorkflowRunResponse.model_validate(run)
    resp.steps = [WorkflowStepResponse.model_validate(s) for s in steps]
    return resp


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunResponse)
async def resume_workflow_run(
    run_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    run = await workflows.resume_workflow_run(session, run_id)
    if not run:
        raise HTTPException(
            status_code=409, detail="Cannot resume this workflow run (must be PAUSED)"
        )

    steps = await workflows.get_run_steps(session, run.id)
    resp = WorkflowRunResponse.model_validate(run)
    resp.steps = [WorkflowStepResponse.model_validate(s) for s in steps]
    return resp


@router.post("/steps/{step_id}/retry", response_model=WorkflowStepResponse)
async def retry_workflow_step(
    step_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    step = await workflows.retry_workflow_step(session, step_id)
    if not step:
        raise HTTPException(status_code=409, detail="Cannot retry this step")
    return WorkflowStepResponse.model_validate(step)


# ── Workflow by ID (must be LAST to avoid catching /runs, /steps as {workflow_id}) ──


@router.get("/{workflow_id}", response_model=WorkflowResponse)
async def get_workflow(
    workflow_id: uuid.UUID, session: AsyncSession = Depends(get_session)
):
    wf = await workflows.get_workflow(session, workflow_id)
    if not wf:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return wf
