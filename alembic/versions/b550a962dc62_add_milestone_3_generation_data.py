"""add milestone 3 generation data

Revision ID: b550a962dc62
Revises: 3d5c121d94ea
Create Date: 2026-07-13 23:06:41.460104
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "b550a962dc62"
down_revision: str | None = "3d5c121d94ea"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _set_sqlite_foreign_keys(*, enabled: bool) -> None:
    """Allow SQLite's move-and-copy batch operation on referenced parent tables."""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        setting = "ON" if enabled else "OFF"
        connection.exec_driver_sql(f"PRAGMA foreign_keys={setting}")


def upgrade() -> None:
    """Apply this revision."""
    _set_sqlite_foreign_keys(enabled=False)
    op.create_table(
        "chapter_versions",
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("generation_metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("(CURRENT_TIMESTAMP)"),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "version > 0",
            name=op.f("ck_chapter_versions_chapter_snapshot_version_positive"),
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapters.id"],
            name=op.f("fk_chapter_versions_chapter_id_chapters"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_chapter_versions")),
        sa.UniqueConstraint("chapter_id", "version", name="chapter_version_number"),
    )
    with op.batch_alter_table("chapter_versions", schema=None) as batch_op:
        batch_op.create_index(
            batch_op.f("ix_chapter_versions_chapter_id"), ["chapter_id"], unique=False
        )

    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.add_column(sa.Column("objective", sa.Text(), server_default="", nullable=False))
        batch_op.add_column(
            sa.Column("outline_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "generation_metadata", sa.JSON(), server_default=sa.text("'{}'"), nullable=False
            )
        )
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "planned",
                "draft",
                "evaluating",
                "needs_revision",
                "accepted",
                "needs_human_review",
                name="chapter_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            type_=sa.Enum(
                "planned",
                "generating",
                "draft",
                "extracting_facts",
                "generated",
                "fact_extraction_failed",
                "failed",
                "evaluating",
                "needs_revision",
                "accepted",
                "needs_human_review",
                name="chapter_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            existing_nullable=False,
        )
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "personality_traits", sa.JSON(), server_default=sa.text("'[]'"), nullable=False
            )
        )

    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("fact_type", sa.String(length=50), server_default="event", nullable=False)
        )

    with op.batch_alter_table("foreshadowings", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("importance", sa.String(length=32), server_default="medium", nullable=False)
        )

    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("language", sa.String(length=32), server_default="zh-CN", nullable=False)
        )
        batch_op.add_column(sa.Column("tone", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("audience", sa.String(length=100), nullable=True))
        batch_op.add_column(sa.Column("logline", sa.Text(), nullable=True))
        batch_op.add_column(
            sa.Column("themes", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
        )
        batch_op.add_column(sa.Column("world_summary", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("central_conflict", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("ending_direction", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("style_guide", sa.Text(), nullable=True))
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "draft",
                "planning",
                "active",
                "completed",
                "archived",
                name="project_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            type_=sa.Enum(
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
            ),
            existing_nullable=False,
        )
    _set_sqlite_foreign_keys(enabled=True)


def downgrade() -> None:
    """Revert this revision."""
    _set_sqlite_foreign_keys(enabled=False)
    op.execute("UPDATE projects SET status='draft' WHERE status IN ('planned', 'failed')")
    op.execute("UPDATE projects SET status='active' WHERE status='generating'")
    with op.batch_alter_table("projects", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
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
            ),
            type_=sa.Enum(
                "draft",
                "planning",
                "active",
                "completed",
                "archived",
                name="project_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            existing_nullable=False,
        )
        batch_op.drop_column("style_guide")
        batch_op.drop_column("ending_direction")
        batch_op.drop_column("central_conflict")
        batch_op.drop_column("world_summary")
        batch_op.drop_column("themes")
        batch_op.drop_column("logline")
        batch_op.drop_column("audience")
        batch_op.drop_column("tone")
        batch_op.drop_column("language")

    with op.batch_alter_table("foreshadowings", schema=None) as batch_op:
        batch_op.drop_column("importance")

    with op.batch_alter_table("facts", schema=None) as batch_op:
        batch_op.drop_column("fact_type")

    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_column("personality_traits")

    op.execute(
        "UPDATE chapters SET status='draft' WHERE status IN "
        "('extracting_facts', 'generated', 'fact_extraction_failed', 'failed')"
    )
    op.execute("UPDATE chapters SET status='planned' WHERE status='generating'")
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=sa.Enum(
                "planned",
                "generating",
                "draft",
                "extracting_facts",
                "generated",
                "fact_extraction_failed",
                "failed",
                "evaluating",
                "needs_revision",
                "accepted",
                "needs_human_review",
                name="chapter_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            type_=sa.Enum(
                "planned",
                "draft",
                "evaluating",
                "needs_revision",
                "accepted",
                "needs_human_review",
                name="chapter_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            existing_nullable=False,
        )
        batch_op.drop_column("generation_metadata")
        batch_op.drop_column("outline_metadata")
        batch_op.drop_column("objective")

    with op.batch_alter_table("chapter_versions", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_chapter_versions_chapter_id"))

    op.drop_table("chapter_versions")
    _set_sqlite_foreign_keys(enabled=True)
