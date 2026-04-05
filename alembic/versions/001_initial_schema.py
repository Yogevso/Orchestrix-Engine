"""initial schema

Revision ID: 001
Revises:
Create Date: 2026-04-05
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Enums
    job_status = sa.Enum(
        "QUEUED", "LEASED", "RUNNING", "SUCCEEDED", "FAILED", "DEAD_LETTER", "CANCELLED",
        name="job_status",
    )
    job_event_type = sa.Enum(
        "CREATED", "QUEUED", "LEASED", "RUNNING", "HEARTBEAT", "SUCCEEDED",
        "FAILED", "RETRIED", "DEAD_LETTERED", "CANCELLED", "REQUEUED",
        name="job_event_type",
    )
    worker_status = sa.Enum("ONLINE", "OFFLINE", "DRAINING", name="worker_status")

    # Jobs
    op.create_table(
        "jobs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("type", sa.String(255), nullable=False),
        sa.Column("queue_name", sa.String(255), nullable=False, server_default="default"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("payload", sa.JSON, nullable=False, server_default="{}"),
        sa.Column("status", job_status, nullable=False, server_default="QUEUED"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer, nullable=False, server_default="3"),
        sa.Column("last_error", sa.Text, nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("worker_id", UUID(as_uuid=True), nullable=True),
        sa.Column("idempotency_key", sa.String(255), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_jobs_type", "jobs", ["type"])
    op.create_index("ix_jobs_queue_name", "jobs", ["queue_name"])
    op.create_index("ix_jobs_pollable", "jobs", ["queue_name", "status", "available_at", "priority"])

    # Job events
    op.create_table(
        "job_events",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("job_id", UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", job_event_type, nullable=False),
        sa.Column("message", sa.Text, nullable=True),
        sa.Column("metadata", sa.JSON, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])

    # Workers
    op.create_table(
        "workers",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("queues", sa.JSON, nullable=False, server_default='["default"]'),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", worker_status, nullable=False, server_default="ONLINE"),
        sa.Column("running_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )


def downgrade() -> None:
    op.drop_table("workers")
    op.drop_table("job_events")
    op.drop_table("jobs")
    op.execute("DROP TYPE IF EXISTS job_status")
    op.execute("DROP TYPE IF EXISTS job_event_type")
    op.execute("DROP TYPE IF EXISTS worker_status")
