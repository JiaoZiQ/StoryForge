"""enforce one active workflow per chapter

Revision ID: c7d4e1a2b9f0
Revises: f2a6c8d91b04
Create Date: 2026-07-14 16:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c7d4e1a2b9f0"
down_revision: str | None = "f2a6c8d91b04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_ACTIVE_WORKFLOW = sa.text("status IN ('pending', 'running', 'paused')")


def upgrade() -> None:
    """Prevent concurrent active workflow rows at the database boundary."""
    op.create_index(
        "uq_workflow_runs_active_chapter",
        "workflow_runs",
        ["chapter_id"],
        unique=True,
        sqlite_where=_ACTIVE_WORKFLOW,
        postgresql_where=_ACTIVE_WORKFLOW,
    )


def downgrade() -> None:
    """Remove the cross-database partial unique index."""
    op.drop_index("uq_workflow_runs_active_chapter", table_name="workflow_runs")
