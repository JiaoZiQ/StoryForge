"""add asynchronous jobs, durable events, transactional outbox, and workers

Revision ID: b61d3f7a2c10
Revises: a91f4d2c7e10
Create Date: 2026-07-18 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b61d3f7a2c10"
down_revision: str | None = "a91f4d2c7e10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _enum(name: str, values: tuple[str, ...], *, length: int = 32) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=length)


def upgrade() -> None:
    op.create_table(
        "jobs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("chapter_id", sa.Integer(), nullable=True),
        sa.Column("workflow_run_id", sa.Integer(), nullable=True),
        sa.Column(
            "job_type",
            _enum(
                "job_type",
                (
                    "generate_plan",
                    "generate_chapter",
                    "evaluate_chapter",
                    "run_chapter_workflow",
                    "resume_workflow",
                    "reindex_memory",
                    "run_retrieval_warmup",
                ),
            ),
            nullable=False,
        ),
        sa.Column("queue_name", sa.String(100), nullable=False),
        sa.Column(
            "status",
            _enum(
                "job_status",
                (
                    "pending",
                    "outbox_pending",
                    "queued",
                    "leased",
                    "running",
                    "pause_requested",
                    "paused",
                    "cancel_requested",
                    "cancelled",
                    "retry_scheduled",
                    "succeeded",
                    "failed",
                    "dead_lettered",
                ),
            ),
            nullable=False,
        ),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_schema_version", sa.Integer(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("result_schema_version", sa.Integer(), nullable=False),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("current_step", sa.String(100), nullable=True),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("queued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancel_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.String(1000), nullable=True),
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("correlation_id", sa.String(64), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key", name="job_idempotency_key"),
        sa.UniqueConstraint("workflow_run_id", name="job_workflow_run"),
        sa.CheckConstraint("priority >= 0 AND priority <= 9", name="job_priority_range"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="job_progress_range"),
        sa.CheckConstraint("attempt >= 0", name="job_attempt_non_negative"),
        sa.CheckConstraint("max_attempts > 0", name="job_max_attempts_positive"),
    )
    for name, columns in (
        ("ix_jobs_project_id", ["project_id"]),
        ("ix_jobs_chapter_id", ["chapter_id"]),
        ("ix_jobs_workflow_run_id", ["workflow_run_id"]),
        ("ix_jobs_job_type", ["job_type"]),
        ("ix_jobs_status", ["status"]),
        ("ix_jobs_correlation_id", ["correlation_id"]),
        ("ix_jobs_status_available_priority", ["status", "available_at", "priority"]),
        ("ix_jobs_project_status", ["project_id", "status"]),
        ("ix_jobs_chapter_status", ["chapter_id", "status"]),
        ("ix_jobs_lease_expires_at", ["lease_expires_at"]),
    ):
        op.create_index(name, "jobs", columns)
    active = sa.text(
        "chapter_id IS NOT NULL AND status IN ('pending','outbox_pending','queued','leased','running','pause_requested','paused','cancel_requested','retry_scheduled')"
    )
    op.create_index(
        "uq_jobs_active_chapter",
        "jobs",
        ["chapter_id"],
        unique=True,
        sqlite_where=active,
        postgresql_where=active,
    )

    op.create_table(
        "job_events",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("job_id", sa.Integer(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column(
            "event_type",
            _enum(
                "job_event_type",
                (
                    "job_created",
                    "job_queued",
                    "job_leased",
                    "job_started",
                    "progress_updated",
                    "workflow_node_started",
                    "workflow_node_completed",
                    "retry_scheduled",
                    "pause_requested",
                    "job_paused",
                    "resume_requested",
                    "cancel_requested",
                    "job_cancelled",
                    "job_succeeded",
                    "job_failed",
                    "job_dead_lettered",
                    "job_discarded",
                ),
                length=40,
            ),
            nullable=False,
        ),
        sa.Column(
            "status",
            _enum(
                "job_event_status",
                (
                    "pending",
                    "outbox_pending",
                    "queued",
                    "leased",
                    "running",
                    "pause_requested",
                    "paused",
                    "cancel_requested",
                    "cancelled",
                    "retry_scheduled",
                    "succeeded",
                    "failed",
                    "dead_lettered",
                ),
            ),
            nullable=False,
        ),
        sa.Column("step", sa.String(100), nullable=True),
        sa.Column("progress", sa.Integer(), nullable=False),
        sa.Column("message_code", sa.String(100), nullable=False),
        sa.Column("message", sa.String(500), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("workflow_event_id", sa.Integer(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_event_id"], ["workflow_events.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "sequence", name="job_event_sequence"),
        sa.CheckConstraint("progress >= 0 AND progress <= 100", name="job_event_progress_range"),
        sa.CheckConstraint("attempt >= 0", name="job_event_attempt_non_negative"),
    )
    op.create_index("ix_job_events_job_id", "job_events", ["job_id"])
    op.create_index("ix_job_events_job_id_id", "job_events", ["job_id", "id"])

    op.create_table(
        "outbox_messages",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("aggregate_type", sa.String(50), nullable=False),
        sa.Column("aggregate_id", sa.Integer(), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column(
            "status",
            _enum("outbox_status", ("pending", "claimed", "published", "failed"), length=16),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column(
            "available_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claimed_by", sa.String(100), nullable=True),
        sa.Column("last_error", sa.String(1000), nullable=True),
        sa.Column("deduplication_key", sa.String(100), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("deduplication_key", name="outbox_deduplication_key"),
        sa.CheckConstraint("attempt >= 0", name="outbox_attempt_non_negative"),
    )
    op.create_index("ix_outbox_messages_aggregate_id", "outbox_messages", ["aggregate_id"])
    op.create_index("ix_outbox_status_available", "outbox_messages", ["status", "available_at"])

    op.create_table(
        "worker_records",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("worker_id", sa.String(100), nullable=False),
        sa.Column("queue_name", sa.String(100), nullable=False),
        sa.Column(
            "status",
            _enum("worker_status", ("starting", "idle", "busy", "stopping", "offline"), length=16),
            nullable=False,
        ),
        sa.Column("current_job_id", sa.Integer(), nullable=True),
        sa.Column(
            "started_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "last_heartbeat_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("version", sa.String(50), nullable=False),
        sa.ForeignKeyConstraint(["current_job_id"], ["jobs.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("worker_id", name="worker_record_worker_id"),
    )
    op.create_index("ix_worker_records_queue_name", "worker_records", ["queue_name"])


def downgrade() -> None:
    op.drop_table("worker_records")
    op.drop_table("outbox_messages")
    op.drop_table("job_events")
    op.drop_table("jobs")
