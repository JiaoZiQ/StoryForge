"""add milestone 4 evaluations and conflicts

Revision ID: ad6fd0f94186
Revises: b550a962dc62
Create Date: 2026-07-14 00:07:43.565271
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "ad6fd0f94186"
down_revision: str | None = "b550a962dc62"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_OLD_CHAPTER_STATUS = sa.Enum(
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
)
_NEW_CHAPTER_STATUS = sa.Enum(
    "planned",
    "generating",
    "draft",
    "extracting_facts",
    "generated",
    "fact_extraction_failed",
    "failed",
    "evaluating",
    "evaluated_passed",
    "evaluated_needs_revision",
    "evaluation_failed",
    "needs_revision",
    "accepted",
    "needs_human_review",
    name="chapter_status",
    native_enum=False,
    create_constraint=True,
    length=32,
)


def _set_sqlite_foreign_keys(*, enabled: bool) -> None:
    """Allow SQLite move-and-copy changes on referenced tables."""
    connection = op.get_bind()
    if connection.dialect.name == "sqlite":
        setting = "ON" if enabled else "OFF"
        connection.exec_driver_sql(f"PRAGMA foreign_keys={setting}")


def upgrade() -> None:
    """Add versioned evaluation details and explainable conflicts."""
    _set_sqlite_foreign_keys(enabled=False)
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_OLD_CHAPTER_STATUS,
            type_=_NEW_CHAPTER_STATUS,
            existing_nullable=False,
        )

    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("knowledge", sa.JSON(), server_default=sa.text("'[]'"), nullable=False)
        )

    with op.batch_alter_table("story_rules", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column(
                "structured_metadata",
                sa.JSON(),
                server_default=sa.text("'{}'"),
                nullable=False,
            )
        )

    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.add_column(sa.Column("evaluation_version", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column(
                "status",
                sa.Enum(
                    "completed",
                    "partial_failed",
                    name="evaluation_status",
                    native_enum=False,
                    create_constraint=False,
                    length=32,
                ),
                server_default="completed",
                nullable=False,
            )
        )
        for name in (
            "mechanical_score",
            "critic_score",
            "pacing_score",
            "dialogue_score",
            "emotional_impact_score",
            "outline_adherence_score",
        ):
            batch_op.add_column(sa.Column(name, sa.Float(), server_default="0", nullable=False))
        for name in (
            "raw_scores",
            "weighted_scores",
            "evaluator_versions",
            "prompt_versions",
        ):
            batch_op.add_column(
                sa.Column(name, sa.JSON(), server_default=sa.text("'{}'"), nullable=False)
            )
        batch_op.add_column(
            sa.Column(
                "blocking_reasons",
                sa.JSON(),
                server_default=sa.text("'[]'"),
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column(
                "recommended_action",
                sa.String(length=32),
                server_default="human_review",
                nullable=False,
            )
        )
        batch_op.add_column(
            sa.Column("passed", sa.Boolean(), server_default=sa.false(), nullable=False)
        )
        batch_op.add_column(
            sa.Column("provider", sa.String(length=100), server_default="legacy", nullable=False)
        )
        batch_op.add_column(
            sa.Column("model", sa.String(length=200), server_default="legacy", nullable=False)
        )
        batch_op.add_column(
            sa.Column(
                "config_version",
                sa.String(length=50),
                server_default="legacy",
                nullable=False,
            )
        )

    op.execute(
        sa.text(
            "UPDATE evaluations SET evaluation_version = "
            "(SELECT COUNT(*) FROM evaluations AS previous "
            "WHERE previous.chapter_id = evaluations.chapter_id "
            "AND previous.id <= evaluations.id)"
        )
    )
    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.alter_column("evaluation_version", existing_type=sa.Integer(), nullable=False)
        batch_op.create_check_constraint("evaluation_version_positive", "evaluation_version > 0")
        batch_op.create_check_constraint(
            "evaluation_status", "status IN ('completed', 'partial_failed')"
        )
        for name in (
            "mechanical_score",
            "critic_score",
            "pacing_score",
            "dialogue_score",
            "emotional_impact_score",
            "outline_adherence_score",
        ):
            batch_op.create_check_constraint(f"{name}_ten_range", f"{name} >= 0 AND {name} <= 10")
        batch_op.create_unique_constraint(
            "evaluation_chapter_version", ["chapter_id", "evaluation_version"]
        )

    op.create_table(
        "consistency_conflicts",
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=False),
        sa.Column(
            "conflict_type",
            sa.Enum(
                "character_state",
                "character_knowledge",
                "character_existence",
                "location",
                "timeline",
                "object_state",
                "story_rule",
                "fact_contradiction",
                "foreshadowing",
                "outline_violation",
                name="conflict_type",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "severity",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="conflict_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("subject", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("new_evidence", sa.Text(), nullable=False),
        sa.Column("existing_evidence", sa.Text(), nullable=True),
        sa.Column("existing_fact_id", sa.Integer(), nullable=True),
        sa.Column("suggested_resolution", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "ignored",
                "resolved",
                "false_positive",
                name="conflict_status",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name=op.f("ck_consistency_conflicts_conflict_confidence_range"),
        ),
        sa.ForeignKeyConstraint(
            ["chapter_id"],
            ["chapters.id"],
            name=op.f("fk_consistency_conflicts_chapter_id_chapters"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_consistency_conflicts_evaluation_id_evaluations"),
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["existing_fact_id"],
            ["facts.id"],
            name=op.f("fk_consistency_conflicts_existing_fact_id_facts"),
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name=op.f("fk_consistency_conflicts_project_id_projects"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_consistency_conflicts")),
    )
    with op.batch_alter_table("consistency_conflicts", schema=None) as batch_op:
        for name in ("chapter_id", "evaluation_id", "existing_fact_id", "project_id"):
            batch_op.create_index(batch_op.f(f"ix_consistency_conflicts_{name}"), [name])

    op.create_table(
        "evaluation_issues",
        sa.Column("evaluation_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=50), nullable=False),
        sa.Column("code", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=False),
        sa.Column(
            "severity",
            sa.Enum(
                "low",
                "medium",
                "high",
                "critical",
                name="issue_severity",
                native_enum=False,
                create_constraint=True,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("evidence", sa.Text(), nullable=True),
        sa.Column("suggestion", sa.Text(), nullable=True),
        sa.Column("score_penalty", sa.Float(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("id", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "score_penalty >= 0 AND score_penalty <= 10",
            name=op.f("ck_evaluation_issues_evaluation_issue_penalty_range"),
        ),
        sa.ForeignKeyConstraint(
            ["evaluation_id"],
            ["evaluations.id"],
            name=op.f("fk_evaluation_issues_evaluation_id_evaluations"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evaluation_issues")),
    )
    with op.batch_alter_table("evaluation_issues", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_evaluation_issues_evaluation_id"), ["evaluation_id"])
    _set_sqlite_foreign_keys(enabled=True)


def downgrade() -> None:
    """Remove milestone-four data while preserving older tables."""
    _set_sqlite_foreign_keys(enabled=False)
    with op.batch_alter_table("evaluation_issues", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_evaluation_issues_evaluation_id"))
    op.drop_table("evaluation_issues")

    with op.batch_alter_table("consistency_conflicts", schema=None) as batch_op:
        for name in ("project_id", "existing_fact_id", "evaluation_id", "chapter_id"):
            batch_op.drop_index(batch_op.f(f"ix_consistency_conflicts_{name}"))
    op.drop_table("consistency_conflicts")

    with op.batch_alter_table("evaluations", schema=None) as batch_op:
        batch_op.drop_constraint("evaluation_chapter_version", type_="unique")
        batch_op.drop_constraint("evaluation_version_positive", type_="check")
        batch_op.drop_constraint("evaluation_status", type_="check")
        for name in (
            "mechanical_score",
            "critic_score",
            "pacing_score",
            "dialogue_score",
            "emotional_impact_score",
            "outline_adherence_score",
        ):
            batch_op.drop_constraint(f"{name}_ten_range", type_="check")
        for name in (
            "config_version",
            "model",
            "provider",
            "passed",
            "recommended_action",
            "blocking_reasons",
            "prompt_versions",
            "evaluator_versions",
            "weighted_scores",
            "raw_scores",
            "outline_adherence_score",
            "emotional_impact_score",
            "dialogue_score",
            "pacing_score",
            "critic_score",
            "mechanical_score",
            "status",
            "evaluation_version",
        ):
            batch_op.drop_column(name)

    with op.batch_alter_table("story_rules", schema=None) as batch_op:
        batch_op.drop_column("structured_metadata")
    with op.batch_alter_table("characters", schema=None) as batch_op:
        batch_op.drop_column("knowledge")
    with op.batch_alter_table("chapters", schema=None) as batch_op:
        batch_op.alter_column(
            "status",
            existing_type=_NEW_CHAPTER_STATUS,
            type_=_OLD_CHAPTER_STATUS,
            existing_nullable=False,
        )
    _set_sqlite_foreign_keys(enabled=True)
