"""add provider governance, usage, budget, and idempotency

Revision ID: a91f4d2c7e10
Revises: e8b4a2f7c913
Create Date: 2026-07-17 20:30:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a91f4d2c7e10"
down_revision: str | None = "e8b4a2f7c913"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _status(name: str, values: tuple[str, ...], *, length: int = 32) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=length)


def _set_sqlite_foreign_keys(*, enabled: bool) -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade() -> None:
    """Add M10 governance state without rewriting earlier revisions."""
    _set_sqlite_foreign_keys(enabled=False)
    with op.batch_alter_table("projects") as batch:
        batch.add_column(
            sa.Column(
                "model_profile",
                sa.String(32),
                nullable=False,
                server_default="offline",
            )
        )
        batch.add_column(
            sa.Column(
                "privacy_policy",
                sa.String(32),
                nullable=False,
                server_default="offline",
            )
        )
    with op.batch_alter_table("projects") as batch:
        batch.alter_column("model_profile", server_default=None)
        batch.alter_column("privacy_policy", server_default=None)
        batch.create_check_constraint(
            op.f("ck_projects_model_profile"),
            "model_profile IN ('offline', 'economy', 'balanced', 'quality')",
        )
        batch.create_check_constraint(
            op.f("ck_projects_privacy_policy"),
            "privacy_policy IN ('offline', 'strict', 'standard')",
        )

    with op.batch_alter_table("workflow_runs") as batch:
        batch.add_column(
            sa.Column("provider_call_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("provider_input_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("provider_output_tokens", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column(
                "provider_estimated_cost",
                sa.Numeric(18, 8),
                nullable=False,
                server_default="0",
            )
        )
        batch.add_column(
            sa.Column("provider_fallback_count", sa.Integer(), nullable=False, server_default="0")
        )
        batch.add_column(
            sa.Column("provider_rate_limit_count", sa.Integer(), nullable=False, server_default="0")
        )
    with op.batch_alter_table("workflow_runs") as batch:
        for column in (
            "provider_call_count",
            "provider_input_tokens",
            "provider_output_tokens",
            "provider_estimated_cost",
            "provider_fallback_count",
            "provider_rate_limit_count",
        ):
            batch.alter_column(column, server_default=None)

    op.create_table(
        "project_budgets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("soft_limit", sa.Numeric(18, 8), nullable=False),
        sa.Column("hard_limit", sa.Numeric(18, 8), nullable=False),
        sa.Column(
            "period",
            _status("budget_period", ("lifetime", "daily", "monthly"), length=16),
            nullable=False,
        ),
        sa.Column("spent_estimated", sa.Numeric(18, 8), nullable=False),
        sa.Column("spent_billed", sa.Numeric(18, 8), nullable=False),
        sa.Column("reserved_estimated", sa.Numeric(18, 8), nullable=False),
        sa.Column("alert_thresholds", sa.JSON(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", name="project_budget_project"),
        sa.CheckConstraint("soft_limit >= 0", name="project_budget_soft_non_negative"),
        sa.CheckConstraint("hard_limit > 0", name="project_budget_hard_positive"),
        sa.CheckConstraint("soft_limit <= hard_limit", name="project_budget_limit_order"),
        sa.CheckConstraint("spent_estimated >= 0", name="project_budget_estimated_non_negative"),
        sa.CheckConstraint("spent_billed >= 0", name="project_budget_billed_non_negative"),
        sa.CheckConstraint("reserved_estimated >= 0", name="project_budget_reserved_non_negative"),
    )
    op.create_index("ix_project_budgets_project_id", "project_budgets", ["project_id"])

    op.create_table(
        "provider_calls",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("workflow_run_id", sa.Integer(), nullable=True),
        sa.Column("chapter_id", sa.Integer(), nullable=True),
        sa.Column("chapter_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "task_type",
            _status(
                "provider_task_type",
                (
                    "planning",
                    "chapter_drafting",
                    "fact_extraction",
                    "graph_extraction",
                    "literary_critique",
                    "revision",
                    "version_comparison",
                    "embedding_document",
                    "embedding_query",
                ),
            ),
            nullable=False,
        ),
        sa.Column("provider", sa.String(100), nullable=False),
        sa.Column("model", sa.String(200), nullable=False),
        sa.Column(
            "profile",
            _status("provider_model_profile", ("offline", "economy", "balanced", "quality")),
            nullable=False,
        ),
        sa.Column(
            "privacy_policy",
            _status("provider_privacy_policy", ("offline", "strict", "standard")),
            nullable=False,
        ),
        sa.Column("prompt_name", sa.String(150), nullable=False),
        sa.Column("prompt_version", sa.String(50), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _status(
                "provider_call_status",
                (
                    "pending",
                    "running",
                    "succeeded",
                    "failed",
                    "rate_limited",
                    "timed_out",
                    "budget_blocked",
                    "circuit_open",
                    "cancelled",
                ),
            ),
            nullable=False,
        ),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("fallback_index", sa.Integer(), nullable=False),
        sa.Column("fallback_reason", sa.String(100), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("cached_input_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column(
            "usage_source",
            _status(
                "token_usage_source",
                ("provider_reported", "local_estimate", "mock", "unknown"),
            ),
            nullable=False,
        ),
        sa.Column("estimated_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("billed_cost", sa.Numeric(18, 8), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False),
        sa.Column("pricing_snapshot", sa.JSON(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=False),
        sa.Column("provider_request_id", sa.String(200), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["chapter_version_id"], ["chapter_versions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "idempotency_key",
            "attempt",
            "fallback_index",
            name="provider_call_attempt_identity",
        ),
        sa.CheckConstraint("attempt > 0", name="provider_call_attempt_positive"),
        sa.CheckConstraint("fallback_index >= 0", name="provider_call_fallback_non_negative"),
        sa.CheckConstraint("input_tokens >= 0", name="provider_call_input_tokens_non_negative"),
        sa.CheckConstraint("output_tokens >= 0", name="provider_call_output_tokens_non_negative"),
        sa.CheckConstraint(
            "cached_input_tokens >= 0", name="provider_call_cached_tokens_non_negative"
        ),
        sa.CheckConstraint("total_tokens >= 0", name="provider_call_total_tokens_non_negative"),
        sa.CheckConstraint("latency_ms >= 0", name="provider_call_latency_non_negative"),
    )
    for column in (
        "project_id",
        "workflow_run_id",
        "chapter_id",
        "chapter_version_id",
        "task_type",
        "provider",
        "model",
        "idempotency_key",
        "status",
    ):
        op.create_index(f"ix_provider_calls_{column}", "provider_calls", [column])

    op.create_table(
        "provider_idempotency_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("idempotency_key", sa.String(64), nullable=False),
        sa.Column(
            "status",
            _status("provider_idempotency_status", ("active", "succeeded", "failed"), length=16),
            nullable=False,
        ),
        sa.Column("provider_call_id", sa.Integer(), nullable=True),
        sa.Column("response_hash", sa.String(64), nullable=True),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["provider_call_id"], ["provider_calls.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("idempotency_key", name="provider_idempotency_key"),
    )
    op.create_index(
        "ix_provider_idempotency_records_idempotency_key",
        "provider_idempotency_records",
        ["idempotency_key"],
    )
    _set_sqlite_foreign_keys(enabled=True)


def downgrade() -> None:
    """Remove M10 governance state while retaining all M1-M9 data."""
    _set_sqlite_foreign_keys(enabled=False)
    op.get_bind().execute(
        sa.text(
            """
            UPDATE chapters
            SET content = COALESCE(
                (SELECT cv.content FROM chapter_versions AS cv
                 WHERE cv.id = chapters.accepted_version_id),
                content
            )
            WHERE accepted_version_id IS NOT NULL
            """
        )
    )
    op.drop_table("provider_idempotency_records")
    op.drop_table("provider_calls")
    op.drop_table("project_budgets")
    with op.batch_alter_table("workflow_runs") as batch:
        for column in (
            "provider_rate_limit_count",
            "provider_fallback_count",
            "provider_estimated_cost",
            "provider_output_tokens",
            "provider_input_tokens",
            "provider_call_count",
        ):
            batch.drop_column(column)
    with op.batch_alter_table("projects") as batch:
        batch.drop_constraint(op.f("ck_projects_privacy_policy"), type_="check")
        batch.drop_constraint(op.f("ck_projects_model_profile"), type_="check")
        batch.drop_column("privacy_policy")
        batch.drop_column("model_profile")
    _set_sqlite_foreign_keys(enabled=True)
