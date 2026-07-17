"""add hybrid vector memory and relational graph

Revision ID: e8b4a2f7c913
Revises: c7d4e1a2b9f0
Create Date: 2026-07-17 10:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision: str = "e8b4a2f7c913"
down_revision: str | None = "c7d4e1a2b9f0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _status(name: str, values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, create_constraint=True, length=32)


def upgrade() -> None:
    """Create portable metadata with a real PostgreSQL vector column and HNSW index."""
    bind = op.get_bind()
    is_postgresql = bind.dialect.name == "postgresql"
    if is_postgresql:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    embedding_type: sa.types.TypeEngine[object] = VECTOR(64) if is_postgresql else sa.JSON()

    op.create_table(
        "memory_chunks",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("chapter_id", sa.Integer(), nullable=True),
        sa.Column("chapter_version_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(50), nullable=False),
        sa.Column("source_id", sa.String(100), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("token_estimate", sa.Integer(), nullable=False),
        sa.Column("character_count", sa.Integer(), nullable=False),
        sa.Column("embedding", embedding_type, nullable=False),
        sa.Column("embedding_provider", sa.String(100), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _status(
                "memory_status",
                ("candidate", "accepted", "rejected", "superseded", "deleted"),
            ),
            nullable=False,
        ),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=False),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["chapter_id"], ["chapters.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["chapter_version_id"], ["chapter_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "chunk_index",
            "content_hash",
            name="memory_chunk_source_hash",
        ),
        sa.CheckConstraint("chunk_index >= 0", name="memory_chunk_index_non_negative"),
        sa.CheckConstraint("token_estimate >= 0", name="memory_chunk_tokens_non_negative"),
        sa.CheckConstraint("character_count >= 0", name="memory_chunk_chars_non_negative"),
        sa.CheckConstraint("embedding_dimensions > 0", name="memory_chunk_dimensions_positive"),
        sa.CheckConstraint("valid_from_chapter > 0", name="memory_chunk_valid_from_positive"),
        sa.CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="memory_chunk_valid_range",
        ),
    )
    for column in ("project_id", "chapter_id", "chapter_version_id", "source_type", "status"):
        op.create_index(f"ix_memory_chunks_{column}", "memory_chunks", [column])
    if is_postgresql:
        op.execute(
            "CREATE INDEX ix_memory_chunks_embedding_hnsw ON memory_chunks "
            "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
        )

    op.create_table(
        "memory_index_records",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("chapter_version_id", sa.Integer(), nullable=False),
        sa.Column(
            "status",
            _status(
                "memory_index_status",
                ("pending", "indexing", "completed", "failed", "superseded"),
            ),
            nullable=False,
        ),
        sa.Column("embedding_provider", sa.String(100), nullable=False),
        sa.Column("embedding_model", sa.String(200), nullable=False),
        sa.Column("embedding_dimensions", sa.Integer(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("graph_entity_count", sa.Integer(), nullable=False),
        sa.Column("graph_relation_count", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["chapter_version_id"], ["chapter_versions.id"], ondelete="CASCADE"
        ),
        sa.UniqueConstraint(
            "chapter_version_id",
            "embedding_provider",
            "embedding_model",
            name="memory_index_version",
        ),
        sa.CheckConstraint("attempt_count >= 0", name="memory_index_attempt_non_negative"),
        sa.CheckConstraint("chunk_count >= 0", name="memory_index_chunks_non_negative"),
    )
    op.create_index("ix_memory_index_records_project_id", "memory_index_records", ["project_id"])
    op.create_index(
        "ix_memory_index_records_chapter_version_id",
        "memory_index_records",
        ["chapter_version_id"],
    )

    op.create_table(
        "graph_entities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column(
            "entity_type",
            _status(
                "graph_entity_type",
                (
                    "character",
                    "location",
                    "object",
                    "event",
                    "secret",
                    "faction",
                    "rule",
                    "foreshadowing",
                    "chapter",
                ),
            ),
            nullable=False,
        ),
        sa.Column("canonical_name", sa.String(200), nullable=False),
        sa.Column("normalized_name", sa.String(200), nullable=False),
        sa.Column("disambiguation_key", sa.String(100), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_chapter_id", sa.Integer(), nullable=True),
        sa.Column("source_version_id", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            _status(
                "graph_entity_status",
                ("candidate", "accepted", "rejected", "superseded", "deleted"),
            ),
            nullable=False,
        ),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("aliases", sa.JSON(), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["chapter_versions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "project_id",
            "entity_type",
            "normalized_name",
            "disambiguation_key",
            name="graph_entity_identity",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="graph_entity_confidence_range"
        ),
    )
    for column in (
        "project_id",
        "normalized_name",
        "source_chapter_id",
        "source_version_id",
        "status",
    ):
        op.create_index(f"ix_graph_entities_{column}", "graph_entities", [column])

    op.create_table(
        "graph_relations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("subject_entity_id", sa.Integer(), nullable=False),
        sa.Column(
            "predicate",
            _status(
                "graph_predicate",
                (
                    "APPEARS_IN",
                    "LOCATED_AT",
                    "KNOWS",
                    "OWNS",
                    "MEMBER_OF",
                    "CAUSED",
                    "PARTICIPATED_IN",
                    "FORESHADOWS",
                    "REVEALS",
                    "CONFLICTS_WITH",
                    "RELATED_TO",
                ),
            ),
            nullable=False,
        ),
        sa.Column("object_entity_id", sa.Integer(), nullable=False),
        sa.Column("source_chapter_id", sa.Integer(), nullable=True),
        sa.Column("source_version_id", sa.Integer(), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("valid_from_chapter", sa.Integer(), nullable=False),
        sa.Column("valid_to_chapter", sa.Integer(), nullable=True),
        sa.Column(
            "status",
            _status(
                "graph_relation_status",
                ("candidate", "accepted", "rejected", "superseded", "deleted"),
            ),
            nullable=False,
        ),
        sa.Column("evidence", sa.Text(), nullable=False),
        sa.Column("evidence_hash", sa.String(64), nullable=False),
        sa.Column("metadata", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["subject_entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["object_entity_id"], ["graph_entities.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_chapter_id"], ["chapters.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_version_id"], ["chapter_versions.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "project_id",
            "subject_entity_id",
            "predicate",
            "object_entity_id",
            "source_version_id",
            "evidence_hash",
            name="graph_relation_evidence_identity",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="graph_relation_confidence_range"
        ),
        sa.CheckConstraint("valid_from_chapter > 0", name="graph_relation_valid_from_positive"),
        sa.CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="graph_relation_valid_range",
        ),
        sa.CheckConstraint(
            "subject_entity_id != object_entity_id", name="graph_relation_distinct_nodes"
        ),
    )
    for column in (
        "project_id",
        "subject_entity_id",
        "object_entity_id",
        "source_chapter_id",
        "source_version_id",
        "status",
    ):
        op.create_index(f"ix_graph_relations_{column}", "graph_relations", [column])


def downgrade() -> None:
    """Remove M8 tables but retain a shared PostgreSQL vector extension."""
    op.drop_table("graph_relations")
    op.drop_table("graph_entities")
    op.drop_table("memory_index_records")
    op.drop_table("memory_chunks")
