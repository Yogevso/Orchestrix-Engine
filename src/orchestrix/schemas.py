import uuid
from datetime import datetime

from pydantic import BaseModel, Field

from orchestrix.models.enums import (
    JobEventType,
    JobStatus,
    WorkerStatus,
    WorkflowStatus,
    WorkflowStepStatus,
)


# ── Jobs ──


class JobCreate(BaseModel):
    type: str = Field(..., examples=["email.send"])
    payload: dict = Field(default_factory=dict)
    queue_name: str = Field(default="default")
    priority: int = Field(default=0, ge=0)
    max_attempts: int = Field(default=3, ge=1, le=20)
    scheduled_at: datetime | None = Field(default=None)
    idempotency_key: str | None = Field(default=None, max_length=255)
    tenant_id: str | None = Field(default=None, max_length=255)


class JobResponse(BaseModel):
    id: uuid.UUID
    type: str
    queue_name: str
    priority: int
    payload: dict
    status: JobStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    scheduled_at: datetime | None
    available_at: datetime
    lease_expires_at: datetime | None
    worker_id: uuid.UUID | None
    idempotency_key: str | None
    tenant_id: str | None
    workflow_step_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class JobListResponse(BaseModel):
    jobs: list[JobResponse]
    total: int


# ── Job Events ──


class JobEventResponse(BaseModel):
    id: uuid.UUID
    job_id: uuid.UUID
    event_type: JobEventType
    message: str | None
    metadata_: dict | None = Field(None)
    created_at: datetime

    model_config = {"from_attributes": True, "populate_by_name": True}


class EventListResponse(BaseModel):
    events: list[JobEventResponse]
    total: int


# ── Workers ──


class WorkerRegister(BaseModel):
    name: str = Field(..., max_length=255)
    queues: list[str] = Field(default=["default"])
    capabilities: list[str] = Field(default_factory=list)
    max_concurrency: int = Field(default=1, ge=1)


class WorkerResponse(BaseModel):
    id: uuid.UUID
    name: str
    queues: list[str]
    capabilities: list[str]
    max_concurrency: int
    last_heartbeat_at: datetime | None
    status: WorkerStatus
    running_count: int
    created_at: datetime

    model_config = {"from_attributes": True}


class PollResponse(BaseModel):
    job: JobResponse | None
    lease_expires_at: datetime | None


class CompleteRequest(BaseModel):
    job_id: uuid.UUID
    result: dict | None = None


class FailRequest(BaseModel):
    job_id: uuid.UUID
    error: str


class HeartbeatRequest(BaseModel):
    job_id: uuid.UUID


# ── Stats ──


class QueueStats(BaseModel):
    queue_name: str
    queued: int = 0
    leased: int = 0
    running: int = 0
    succeeded: int = 0
    failed: int = 0
    dead_letter: int = 0


# ── Queue Config ──


class QueueConfigCreate(BaseModel):
    queue_name: str = Field(..., max_length=255)
    max_concurrency: int | None = Field(default=None, ge=1)
    rate_limit_per_second: int | None = Field(default=None, ge=1)


class QueueConfigResponse(BaseModel):
    id: uuid.UUID
    queue_name: str
    max_concurrency: int | None
    rate_limit_per_second: int | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


# ── Recurring Jobs ──


class RecurringJobCreate(BaseModel):
    name: str = Field(..., max_length=255)
    type: str = Field(..., max_length=255)
    payload: dict = Field(default_factory=dict)
    queue_name: str = Field(default="default")
    cron_expression: str = Field(..., examples=["*/5 * * * *"])
    max_attempts: int = Field(default=3, ge=1, le=20)
    tenant_id: str | None = Field(default=None)


class RecurringJobResponse(BaseModel):
    id: uuid.UUID
    name: str
    type: str
    payload: dict
    queue_name: str
    cron_expression: str
    max_attempts: int
    enabled: bool
    tenant_id: str | None
    last_run_at: datetime | None
    next_run_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class RecurringJobToggle(BaseModel):
    enabled: bool


# ── Workflows (Phase 3) ──


class WorkflowStepDef(BaseModel):
    """A single step within a workflow definition."""

    name: str = Field(..., max_length=255)
    job_type: str = Field(..., max_length=255)
    payload: dict = Field(default_factory=dict)
    depends_on: list[str] = Field(default_factory=list)
    max_attempts: int = Field(default=3, ge=1, le=20)


class WorkflowCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    steps: list[WorkflowStepDef] = Field(..., min_length=1)
    tenant_id: str | None = None


class WorkflowResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: str | None
    definition: dict
    tenant_id: str | None
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunCreate(BaseModel):
    workflow_id: uuid.UUID
    input_payload: dict = Field(default_factory=dict)
    tenant_id: str | None = None


class WorkflowStepResponse(BaseModel):
    id: uuid.UUID
    workflow_run_id: uuid.UUID
    step_name: str
    job_type: str
    payload: dict
    depends_on: list[str]
    status: WorkflowStepStatus
    attempts: int
    max_attempts: int
    last_error: str | None
    result: dict | None
    job_id: uuid.UUID | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}


class WorkflowRunResponse(BaseModel):
    id: uuid.UUID
    workflow_id: uuid.UUID
    status: WorkflowStatus
    input_payload: dict
    output: dict | None
    tenant_id: str | None
    started_at: datetime | None
    finished_at: datetime | None
    created_at: datetime
    updated_at: datetime
    steps: list[WorkflowStepResponse] = Field(default_factory=list)

    model_config = {"from_attributes": True}
