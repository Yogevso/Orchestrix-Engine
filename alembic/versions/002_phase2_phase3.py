"""Phase 2 + 3 schema: queues, recurring jobs, workflows

Revision ID: 002
Revises: 001
Create Date: 2026-04-06
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── New enums ──
    workflow_status = sa.Enum(
        "PENDING", "RUNNING", "SUCCEEDED", "FAILED", "CANCELLED", "PAUSED",
        name="workflow_status",
    )
    workflow_step_status = sa.Enum(
        "PENDING", "QUEUED", "RUNNING", "SUCCEEDED", "FAILED", "SKIPPED", "CANCELLED",
        name="workflow_step_status",
    )

    # ── Existing table alterations ──

    # Jobs: add tenant_id, workflow_step_id
    op.add_column("jobs", sa.Column("tenant_id", sa.String(255), nullable=True))
    op.add_column("jobs", sa.Column("workflow_step_id", UUID(as_uuid=True), nullable=True))
    op.create_index("ix_jobs_tenant_id", "jobs", ["tenant_id"])
    op.create_index("ix_jobs_workflow_step_id", "jobs", ["workflow_step_id"])
    op.create_index("ix_jobs_tenant_status", "jobs", ["tenant_id", "status"])

    # Workers: add capabilities, max_concurrency
    op.add_column("workers", sa.Column("capabilities", sa.JSON, nullable=False, server_default="[]"))
    op.add_column("workers", sa.Column("max_concurrency", sa.Integer, nullable=False, server_default="1"))

    # ── Queue configs ──
    op.create_table(
        "queue_configs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("queue_name", sa.String(255), nullable=False, unique=True),
        sa.Column("max_concurrency", sa.Integer, nullable=True),
        sa.Column("rate_limit_per_second", sa.Integer, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── Recurring jobs ──
    op.create_table(
        "recurring_jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("queue_name", sa.String(255), nullable=False, server_default="default"),
        sa.Column("cron_expression", sa.String(255), nullable=False),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("enabled", sa.Boolean, nullable=False, server_default=sa.text("true")),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_recurring_jobs_next_run_at", "recurring_jobs", ["next_run_at"])

    # ── Workflows ──
    op.create_table(
        "workflows",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False, unique=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("definition", sa.JSON, nullable=False),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # ── Workflow runs ──
    op.create_table(
        "workflow_runs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_id", UUID(as_uuid=True), sa.ForeignKey("workflows.id"), nullable=False),
        sa.Column("status", workflow_status, nullable=False, server_default="PENDING"),
        sa.Column("input_payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("output", sa.JSON, nullable=True),
        sa.Column("tenant_id", sa.String(255), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_tenant_id", "workflow_runs", ["tenant_id"])

    # ── Workflow steps ──
    op.create_table(
        "workflow_steps",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("workflow_run_id", UUID(as_uuid=True), sa.ForeignKey("workflow_runs.id"), nullable=False),
        sa.Column("step_name", sa.String(255), nullable=False),
        sa.Column("job_type", sa.String(255), nullable=False),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("depends_on", sa.JSON, nullable=False, server_default="[]"),
        sa.Column("status", workflow_step_status, nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("result", sa.JSON, nullable=True),
        sa.Column("job_id", UUID(as_uuid=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_workflow_steps_run_id", "workflow_steps", ["workflow_run_id"])


def downgrade() -> None:
    op.drop_table("workflow_steps")
    op.drop_table("workflow_runs")
    op.drop_table("workflows")
    op.drop_table("recurring_jobs")
    op.drop_table("queue_configs")
    op.drop_index("ix_jobs_tenant_status", table_name="jobs")
    op.drop_index("ix_jobs_workflow_step_id", table_name="jobs")
    op.drop_index("ix_jobs_tenant_id", table_name="jobs")
    op.drop_column("jobs", "workflow_step_id")
    op.drop_column("jobs", "tenant_id")
    op.drop_column("workers", "max_concurrency")
    op.drop_column("workers", "capabilities")
    op.execute("DROP TYPE IF EXISTS workflow_status")
    op.execute("DROP TYPE IF EXISTS workflow_step_status")
