"""add milestone 6 API metadata

Revision ID: f2a6c8d91b04
Revises: 69c75316dd7e
Create Date: 2026-07-14 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a6c8d91b04"
down_revision: str | None = "69c75316dd7e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_M5_PROJECT_STATUS = sa.Enum(
    "draft",
    "planning",
    "planned",
    "generating",
    "active",
    "completed",
    "failed",
    "archived",
    name="project_status",
    native_enum=False,
    create_constraint=True,
    length=32,
)
_M6_PROJECT_STATUS = sa.Enum(
    "created",
    *_M5_PROJECT_STATUS.enums,
    name="project_status",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def _set_sqlite_foreign_keys(*, enabled: bool) -> None:
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        connection.exec_driver_sql(f"PRAGMA foreign_keys={'ON' if enabled else 'OFF'}")


def upgrade() -> None:
    """Add only metadata required by the stable M6 application boundary."""
    _set_sqlite_foreign_keys(enabled=False)
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "additional_requirements",
                sa.Text(),
                server_default=sa.text("''"),
                nullable=False,
            )
        )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_M5_PROJECT_STATUS,
            type_=_M6_PROJECT_STATUS,
            existing_nullable=False,
        )
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.alter_column(
            "additional_requirements",
            existing_type=sa.Text(),
            existing_nullable=False,
            server_default=None,
        )

    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "mechanical_metrics",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "critic_dimensions",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )
    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.alter_column(
            "mechanical_metrics",
            existing_type=sa.JSON(),
            existing_nullable=False,
            server_default=None,
        )
        batch_op.alter_column(
            "critic_dimensions",
            existing_type=sa.JSON(),
            existing_nullable=False,
            server_default=None,
        )

    with op.batch_alter_table("consistency_conflicts", schema=None) as batch_op:
        batch_op.add_column(sa.Column("resolution_note", sa.Text(), nullable=True))
    _set_sqlite_foreign_keys(enabled=True)


def downgrade() -> None:
    """Return to the exact M5 schema while preserving compatible data."""
    _set_sqlite_foreign_keys(enabled=False)
    with op.batch_alter_table("consistency_conflicts", schema=None) as batch_op:
        batch_op.drop_column("resolution_note")
    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.drop_column("critic_dimensions")
        batch_op.drop_column("mechanical_metrics")
    op.execute("UPDATE projects SET status='draft' WHERE status='created'")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_M6_PROJECT_STATUS,
            type_=_M5_PROJECT_STATUS,
            existing_nullable=False,
        )
        batch_op.drop_column("additional_requirements")
    _set_sqlite_foreign_keys(enabled=True)
