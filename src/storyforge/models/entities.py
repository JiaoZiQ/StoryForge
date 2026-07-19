"""SQLAlchemy 2 mappings for the StoryForge domain."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PythonEnum
from typing import Any
from uuid import uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storyforge.enums import (
    BudgetPeriod,
    ChapterStatus,
    ChapterVersionStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    FactStatus,
    ForeshadowingStatus,
    GraphEntityType,
    GraphPredicate,
    IdempotencyStatus,
    JobEventType,
    JobStatus,
    JobType,
    MemoryIndexStatus,
    MemoryStatus,
    ModelProfile,
    OutboxStatus,
    PrivacyPolicy,
    ProjectStatus,
    ProviderCallStatus,
    TaskType,
    TokenUsageSource,
    WorkerStatus,
    WorkflowEventType,
    WorkflowRunStatus,
)
from storyforge.models.base import EntityBase, TimestampMixin, utc_now


def _enum_values(enum_class: type[PythonEnum]) -> list[str]:
    """Persist string enum values instead of Python member names."""
    return [str(member.value) for member in enum_class]


class Project(TimestampMixin, EntityBase):
    """A long-form fiction project and root of its persisted story data."""

    __tablename__ = "projects"
    __table_args__ = (
        CheckConstraint("target_chapters > 0", name="target_chapters_positive"),
        CheckConstraint(
            "target_words_per_chapter > 0",
            name="target_words_per_chapter_positive",
        ),
    )

    title: Mapped[str] = mapped_column(String(200), nullable=False)
    genre: Mapped[str] = mapped_column(String(100), nullable=False)
    premise: Mapped[str] = mapped_column(Text, nullable=False)
    target_chapters: Mapped[int] = mapped_column(nullable=False)
    target_words_per_chapter: Mapped[int] = mapped_column(nullable=False)
    language: Mapped[str] = mapped_column(String(32), default="zh-CN", nullable=False)
    tone: Mapped[str | None] = mapped_column(String(100), nullable=True)
    audience: Mapped[str | None] = mapped_column(String(100), nullable=True)
    additional_requirements: Mapped[str] = mapped_column(Text, default="", nullable=False)
    logline: Mapped[str | None] = mapped_column(Text, nullable=True)
    themes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    world_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    central_conflict: Mapped[str | None] = mapped_column(Text, nullable=True)
    ending_direction: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_guide: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ProjectStatus] = mapped_column(
        SQLAlchemyEnum(
            ProjectStatus,
            name="project_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ProjectStatus.CREATED,
        nullable=False,
    )
    model_profile: Mapped[ModelProfile] = mapped_column(
        SQLAlchemyEnum(
            ModelProfile,
            name="model_profile",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ModelProfile.OFFLINE,
        nullable=False,
    )
    privacy_policy: Mapped[PrivacyPolicy] = mapped_column(
        SQLAlchemyEnum(
            PrivacyPolicy,
            name="privacy_policy",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=PrivacyPolicy.OFFLINE,
        nullable=False,
    )

    characters: Mapped[list[Character]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    locations: Mapped[list[Location]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    story_rules: Mapped[list[StoryRule]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    chapters: Mapped[list[Chapter]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Chapter.chapter_number",
    )
    facts: Mapped[list[Fact]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    foreshadowings: Mapped[list[Foreshadowing]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="project",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    memory_chunks: Mapped[list[MemoryChunk]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    memory_index_records: Mapped[list[MemoryIndexRecord]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    graph_entities: Mapped[list[GraphEntity]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class Character(EntityBase):
    """A named character belonging to one project."""

    __tablename__ = "characters"
    __table_args__ = (UniqueConstraint("project_id", "name", name="character_project_name"),)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    role: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    goals: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    personality: Mapped[str] = mapped_column(Text, nullable=False)
    personality_traits: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    speech_style: Mapped[str] = mapped_column(Text, nullable=False)
    current_state: Mapped[str] = mapped_column(Text, nullable=False)
    secrets: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    knowledge: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    project: Mapped[Project] = relationship(back_populates="characters")


class Location(EntityBase):
    """A story location and its local rules."""

    __tablename__ = "locations"
    __table_args__ = (UniqueConstraint("project_id", "name", name="location_project_name"),)

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    name: Mapped[str] = mapped_column(String(150), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    rules: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)

    project: Mapped[Project] = relationship(back_populates="locations")


class StoryRule(EntityBase):
    """A persisted world, style, or continuity rule."""

    __tablename__ = "story_rules"

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(String(200), nullable=False)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    structured_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)

    project: Mapped[Project] = relationship(back_populates="story_rules")


class Chapter(TimestampMixin, EntityBase):
    """A versioned chapter within a project."""

    __tablename__ = "chapters"
    __table_args__ = (
        UniqueConstraint("project_id", "chapter_number", name="chapter_project_number"),
        CheckConstraint("chapter_number > 0", name="chapter_number_positive"),
        CheckConstraint("version > 0", name="chapter_version_positive"),
        CheckConstraint(
            "score IS NULL OR (score >= 0 AND score <= 100)",
            name="chapter_score_range",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    outline: Mapped[str] = mapped_column(Text, nullable=False)
    objective: Mapped[str] = mapped_column(Text, default="", nullable=False)
    outline_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[ChapterStatus] = mapped_column(
        SQLAlchemyEnum(
            ChapterStatus,
            name="chapter_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ChapterStatus.PLANNED,
        nullable=False,
    )
    version: Mapped[int] = mapped_column(default=1, nullable=False)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_chapters_current_version_id_chapter_versions",
        ),
        nullable=True,
    )
    accepted_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_chapters_accepted_version_id_chapter_versions",
        ),
        nullable=True,
    )

    project: Mapped[Project] = relationship(back_populates="chapters")
    facts: Mapped[list[Fact]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    revisions: Mapped[list[Revision]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Revision.new_version",
    )
    versions: Mapped[list[ChapterVersion]] = relationship(
        back_populates="chapter",
        foreign_keys="ChapterVersion.chapter_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChapterVersion.version",
    )
    current_version: Mapped[ChapterVersion | None] = relationship(
        foreign_keys=[current_version_id], post_update=True
    )
    accepted_version: Mapped[ChapterVersion | None] = relationship(
        foreign_keys=[accepted_version_id], post_update=True
    )
    workflow_runs: Mapped[list[WorkflowRun]] = relationship(
        back_populates="chapter",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Fact(EntityBase):
    """A structured fact with a bounded chapter-validity interval."""

    __tablename__ = "facts"
    __table_args__ = (
        CheckConstraint("valid_from_chapter > 0", name="fact_valid_from_positive"),
        CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="fact_valid_range",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="fact_confidence_range",
        ),
        UniqueConstraint(
            "chapter_version_id", "normalized_hash", name="fact_version_normalized_hash"
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    predicate: Mapped[str] = mapped_column(String(200), nullable=False)
    object: Mapped[str] = mapped_column(Text, nullable=False)
    valid_from_chapter: Mapped[int] = mapped_column(nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(nullable=True)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    source_quote: Mapped[str] = mapped_column(Text, nullable=False)
    fact_type: Mapped[str] = mapped_column(String(50), default="event", nullable=False)
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "workflow_runs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_chapter_versions_workflow_run_id_workflow_runs",
        ),
        index=True,
        nullable=True,
    )
    status: Mapped[FactStatus] = mapped_column(
        SQLAlchemyEnum(
            FactStatus,
            name="fact_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=FactStatus.ACCEPTED,
        nullable=False,
    )
    normalized_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    project: Mapped[Project] = relationship(back_populates="facts")
    chapter: Mapped[Chapter] = relationship(back_populates="facts")
    chapter_version: Mapped[ChapterVersion] = relationship(back_populates="facts")
    referenced_conflicts: Mapped[list[Conflict]] = relationship(
        back_populates="existing_fact",
        passive_deletes=True,
    )


class Foreshadowing(EntityBase):
    """A planned setup and optional payoff tracked by chapter number."""

    __tablename__ = "foreshadowings"
    __table_args__ = (
        CheckConstraint("setup_chapter > 0", name="foreshadowing_setup_positive"),
        CheckConstraint(
            "expected_payoff_chapter >= setup_chapter",
            name="foreshadowing_expected_range",
        ),
        CheckConstraint(
            "payoff_chapter IS NULL OR payoff_chapter >= setup_chapter",
            name="foreshadowing_payoff_range",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    setup_chapter: Mapped[int] = mapped_column(nullable=False)
    expected_payoff_chapter: Mapped[int] = mapped_column(nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ForeshadowingStatus] = mapped_column(
        SQLAlchemyEnum(
            ForeshadowingStatus,
            name="foreshadowing_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ForeshadowingStatus.PLANNED,
        nullable=False,
    )
    payoff_chapter: Mapped[int | None] = mapped_column(nullable=True)
    importance: Mapped[str] = mapped_column(String(32), default="medium", nullable=False)

    project: Mapped[Project] = relationship(back_populates="foreshadowings")


class ChapterVersion(EntityBase):
    """Immutable full-text snapshot for one generated chapter version."""

    __tablename__ = "chapter_versions"
    __table_args__ = (
        UniqueConstraint("chapter_id", "version", name="chapter_version_number"),
        UniqueConstraint("idempotency_key", name="chapter_version_idempotency_key"),
        CheckConstraint("version > 0", name="chapter_snapshot_version_positive"),
    )

    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    version: Mapped[int] = mapped_column(nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    generation_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[ChapterVersionStatus] = mapped_column(
        SQLAlchemyEnum(
            ChapterVersionStatus,
            name="chapter_version_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ChapterVersionStatus.DRAFT,
        nullable=False,
    )
    source: Mapped[str] = mapped_column(String(32), default="generated", nullable=False)
    parent_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    word_count: Mapped[int] = mapped_column(default=0, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="legacy", nullable=False)
    model: Mapped[str] = mapped_column(String(200), default="legacy", nullable=False)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    candidate_character_updates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    candidate_foreshadowing_updates: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    chapter: Mapped[Chapter] = relationship(back_populates="versions", foreign_keys=[chapter_id])
    parent_version: Mapped[ChapterVersion | None] = relationship(
        remote_side="ChapterVersion.id", foreign_keys=[parent_version_id]
    )
    facts: Mapped[list[Fact]] = relationship(
        back_populates="chapter_version", cascade="all, delete-orphan", passive_deletes=True
    )
    evaluations: Mapped[list[Evaluation]] = relationship(
        back_populates="chapter_version", cascade="all, delete-orphan", passive_deletes=True
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        back_populates="chapter_version", passive_deletes=True
    )
    memory_chunks: Mapped[list[MemoryChunk]] = relationship(
        back_populates="chapter_version", cascade="all, delete-orphan", passive_deletes=True
    )
    memory_index_records: Mapped[list[MemoryIndexRecord]] = relationship(
        back_populates="chapter_version", cascade="all, delete-orphan", passive_deletes=True
    )
    graph_entities: Mapped[list[GraphEntity]] = relationship(
        back_populates="source_version", passive_deletes=True
    )
    graph_relations: Mapped[list[GraphRelation]] = relationship(
        back_populates="source_version", passive_deletes=True
    )


class MemoryChunk(EntityBase):
    """A bounded, version-aware semantic memory fragment."""

    __tablename__ = "memory_chunks"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "source_type",
            "source_id",
            "chunk_index",
            "content_hash",
            name="memory_chunk_source_hash",
        ),
        CheckConstraint("chunk_index >= 0", name="memory_chunk_index_non_negative"),
        CheckConstraint("token_estimate >= 0", name="memory_chunk_tokens_non_negative"),
        CheckConstraint("character_count >= 0", name="memory_chunk_chars_non_negative"),
        CheckConstraint("embedding_dimensions > 0", name="memory_chunk_dimensions_positive"),
        CheckConstraint("valid_from_chapter > 0", name="memory_chunk_valid_from_positive"),
        CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="memory_chunk_valid_range",
        ),
        Index(
            "ix_memory_chunks_embedding_hnsw",
            "embedding",
            postgresql_using="hnsw",
            postgresql_with={"m": 16, "ef_construction": 64},
            postgresql_ops={"embedding": "vector_cosine_ops"},
        ).ddl_if(dialect="postgresql"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=True
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=True
    )
    source_type: Mapped[str] = mapped_column(String(50), index=True, nullable=False)
    source_id: Mapped[str] = mapped_column(String(100), nullable=False)
    chunk_index: Mapped[int] = mapped_column(nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    token_estimate: Mapped[int] = mapped_column(nullable=False)
    character_count: Mapped[int] = mapped_column(nullable=False)
    embedding: Mapped[list[float]] = mapped_column(
        JSON().with_variant(VECTOR(64), "postgresql"), nullable=False
    )
    embedding_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[MemoryStatus] = mapped_column(
        SQLAlchemyEnum(
            MemoryStatus,
            name="memory_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=MemoryStatus.ACCEPTED,
        index=True,
        nullable=False,
    )
    valid_from_chapter: Mapped[int] = mapped_column(nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(nullable=True)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="memory_chunks")
    chapter_version: Mapped[ChapterVersion | None] = relationship(back_populates="memory_chunks")


class MemoryIndexRecord(EntityBase):
    """Auditable synchronous index attempt with explicit retry state."""

    __tablename__ = "memory_index_records"
    __table_args__ = (
        UniqueConstraint(
            "chapter_version_id",
            "embedding_provider",
            "embedding_model",
            name="memory_index_version",
        ),
        CheckConstraint("attempt_count >= 0", name="memory_index_attempt_non_negative"),
        CheckConstraint("chunk_count >= 0", name="memory_index_chunks_non_negative"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[MemoryIndexStatus] = mapped_column(
        SQLAlchemyEnum(
            MemoryIndexStatus,
            name="memory_index_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=MemoryIndexStatus.PENDING,
        nullable=False,
    )
    embedding_provider: Mapped[str] = mapped_column(String(100), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(200), nullable=False)
    embedding_dimensions: Mapped[int] = mapped_column(nullable=False)
    attempt_count: Mapped[int] = mapped_column(default=0, nullable=False)
    chunk_count: Mapped[int] = mapped_column(default=0, nullable=False)
    graph_entity_count: Mapped[int] = mapped_column(default=0, nullable=False)
    graph_relation_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="memory_index_records")
    chapter_version: Mapped[ChapterVersion] = relationship(back_populates="memory_index_records")


class GraphEntity(EntityBase):
    """A canonical project-scoped graph node backed by accepted story evidence."""

    __tablename__ = "graph_entities"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "entity_type",
            "normalized_name",
            "disambiguation_key",
            name="graph_entity_identity",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="graph_entity_confidence_range"
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    entity_type: Mapped[GraphEntityType] = mapped_column(
        SQLAlchemyEnum(
            GraphEntityType,
            name="graph_entity_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    canonical_name: Mapped[str] = mapped_column(String(200), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    disambiguation_key: Mapped[str] = mapped_column(String(100), default="", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), index=True, nullable=True
    )
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[MemoryStatus] = mapped_column(
        SQLAlchemyEnum(
            MemoryStatus,
            name="graph_entity_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=MemoryStatus.ACCEPTED,
        index=True,
        nullable=False,
    )
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    project: Mapped[Project] = relationship(back_populates="graph_entities")
    source_version: Mapped[ChapterVersion | None] = relationship(back_populates="graph_entities")
    outgoing_relations: Mapped[list[GraphRelation]] = relationship(
        back_populates="subject_entity",
        foreign_keys="GraphRelation.subject_entity_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )
    incoming_relations: Mapped[list[GraphRelation]] = relationship(
        back_populates="object_entity",
        foreign_keys="GraphRelation.object_entity_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class GraphRelation(EntityBase):
    """A bounded, explainable edge in the PostgreSQL-backed story graph."""

    __tablename__ = "graph_relations"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "subject_entity_id",
            "predicate",
            "object_entity_id",
            "source_version_id",
            "evidence_hash",
            name="graph_relation_evidence_identity",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1", name="graph_relation_confidence_range"
        ),
        CheckConstraint("valid_from_chapter > 0", name="graph_relation_valid_from_positive"),
        CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="graph_relation_valid_range",
        ),
        CheckConstraint(
            "subject_entity_id != object_entity_id", name="graph_relation_distinct_nodes"
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_entity_id: Mapped[int] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    predicate: Mapped[GraphPredicate] = mapped_column(
        SQLAlchemyEnum(
            GraphPredicate,
            name="graph_predicate",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    object_entity_id: Mapped[int] = mapped_column(
        ForeignKey("graph_entities.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source_chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), index=True, nullable=True
    )
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    valid_from_chapter: Mapped[int] = mapped_column(nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[MemoryStatus] = mapped_column(
        SQLAlchemyEnum(
            MemoryStatus,
            name="graph_relation_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=MemoryStatus.ACCEPTED,
        index=True,
        nullable=False,
    )
    evidence: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    subject_entity: Mapped[GraphEntity] = relationship(
        back_populates="outgoing_relations", foreign_keys=[subject_entity_id]
    )
    object_entity: Mapped[GraphEntity] = relationship(
        back_populates="incoming_relations", foreign_keys=[object_entity_id]
    )
    source_version: Mapped[ChapterVersion | None] = relationship(back_populates="graph_relations")


class Evaluation(EntityBase):
    """Structured chapter quality scores and revision guidance."""

    __tablename__ = "evaluations"
    __table_args__ = (
        *tuple(
            CheckConstraint(
                f"{column} >= 0 AND {column} <= 100",
                name=f"{column}_range",
            )
            for column in (
                "overall_score",
                "consistency_score",
                "prose_score",
                "character_score",
                "plot_score",
            )
        ),
        CheckConstraint("evaluation_version > 0", name="evaluation_version_positive"),
        *tuple(
            CheckConstraint(
                f"{column} >= 0 AND {column} <= 10",
                name=f"{column}_ten_range",
            )
            for column in (
                "mechanical_score",
                "critic_score",
                "pacing_score",
                "dialogue_score",
                "emotional_impact_score",
                "outline_adherence_score",
            )
        ),
        UniqueConstraint("chapter_id", "evaluation_version", name="evaluation_chapter_version"),
        UniqueConstraint("idempotency_key", name="evaluation_idempotency_key"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    idempotency_key: Mapped[str | None] = mapped_column(String(200), nullable=True)
    evaluator: Mapped[str] = mapped_column(String(200), nullable=False)
    evaluation_version: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        SQLAlchemyEnum(
            EvaluationStatus,
            name="evaluation_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=EvaluationStatus.COMPLETED,
        nullable=False,
    )
    overall_score: Mapped[float] = mapped_column(Float, nullable=False)
    mechanical_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    critic_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    consistency_score: Mapped[float] = mapped_column(Float, nullable=False)
    prose_score: Mapped[float] = mapped_column(Float, nullable=False)
    character_score: Mapped[float] = mapped_column(Float, nullable=False)
    plot_score: Mapped[float] = mapped_column(Float, nullable=False)
    pacing_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    dialogue_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    emotional_impact_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    outline_adherence_score: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    raw_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    weighted_scores: Mapped[dict[str, float]] = mapped_column(JSON, default=dict, nullable=False)
    mechanical_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    critic_dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluator_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recommended_action: Mapped[str] = mapped_column(
        String(32), default="human_review", nullable=False
    )
    passed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    provider: Mapped[str] = mapped_column(String(100), default="legacy", nullable=False)
    model: Mapped[str] = mapped_column(String(200), default="legacy", nullable=False)
    config_version: Mapped[str] = mapped_column(String(50), default="legacy", nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    suggestions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    project: Mapped[Project] = relationship(back_populates="evaluations")
    chapter: Mapped[Chapter] = relationship(back_populates="evaluations")
    chapter_version: Mapped[ChapterVersion] = relationship(back_populates="evaluations")
    issue_records: Mapped[list[EvaluationIssue]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="EvaluationIssue.id",
    )
    conflicts: Mapped[list[Conflict]] = relationship(
        back_populates="evaluation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Conflict.id",
    )


class EvaluationIssue(EntityBase):
    """One normalized issue produced by a mechanical or LLM evaluator."""

    __tablename__ = "evaluation_issues"
    __table_args__ = (
        CheckConstraint(
            "score_penalty >= 0 AND score_penalty <= 10",
            name="evaluation_issue_penalty_range",
        ),
    )

    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    source: Mapped[str] = mapped_column(String(50), nullable=False)
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[ConflictSeverity] = mapped_column(
        SQLAlchemyEnum(
            ConflictSeverity,
            name="issue_severity",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggestion: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_penalty: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    details: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    evaluation: Mapped[Evaluation] = relationship(back_populates="issue_records")


class Conflict(EntityBase):
    """Persisted, explainable consistency conflict for one evaluation."""

    __tablename__ = "consistency_conflicts"
    __table_args__ = (
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="conflict_confidence_range"),
    )

    evaluation_id: Mapped[int] = mapped_column(
        ForeignKey("evaluations.id", ondelete="CASCADE"), index=True, nullable=False
    )
    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    conflict_type: Mapped[ConflictType] = mapped_column(
        SQLAlchemyEnum(
            ConflictType,
            name="conflict_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    severity: Mapped[ConflictSeverity] = mapped_column(
        SQLAlchemyEnum(
            ConflictSeverity,
            name="conflict_severity",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    subject: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    new_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    existing_evidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    existing_fact_id: Mapped[int | None] = mapped_column(
        ForeignKey("facts.id", ondelete="SET NULL"), index=True, nullable=True
    )
    suggested_resolution: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rule_code: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[ConflictStatus] = mapped_column(
        SQLAlchemyEnum(
            ConflictStatus,
            name="conflict_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ConflictStatus.OPEN,
        nullable=False,
    )
    resolution_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="conflicts")
    project: Mapped[Project] = relationship(back_populates="conflicts")
    chapter: Mapped[Chapter] = relationship(back_populates="conflicts")
    chapter_version: Mapped[ChapterVersion] = relationship(back_populates="conflicts")
    existing_fact: Mapped[Fact | None] = relationship(back_populates="referenced_conflicts")


class Revision(EntityBase):
    """A recorded transition between two chapter versions."""

    __tablename__ = "revisions"
    __table_args__ = (
        UniqueConstraint(
            "chapter_id",
            "new_version",
            name="revision_chapter_new_version",
        ),
        CheckConstraint("previous_version > 0", name="revision_previous_positive"),
        CheckConstraint(
            "new_version > previous_version",
            name="revision_version_progression",
        ),
        CheckConstraint(
            "score_before >= 0 AND score_before <= 100",
            name="revision_score_before_range",
        ),
        CheckConstraint(
            "score_after >= 0 AND score_after <= 100",
            name="revision_score_after_range",
        ),
    )

    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    previous_version: Mapped[int] = mapped_column(nullable=False)
    new_version: Mapped[int] = mapped_column(nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    score_before: Mapped[float] = mapped_column(Float, nullable=False)
    score_after: Mapped[float] = mapped_column(Float, nullable=False)
    accepted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    source_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    new_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    status: Mapped[str] = mapped_column(String(32), default="created", nullable=False)
    brief: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    chapter: Mapped[Chapter] = relationship(back_populates="revisions")


class WorkflowRun(EntityBase):
    """A durable execution log record for a project/chapter workflow."""

    __tablename__ = "workflow_runs"
    __table_args__ = (
        CheckConstraint("retry_count >= 0", name="workflow_retry_non_negative"),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="workflow_finished_after_start",
        ),
        Index(
            "uq_workflow_runs_active_chapter",
            "chapter_id",
            unique=True,
            sqlite_where=text("status IN ('pending', 'running', 'paused')"),
            postgresql_where=text("status IN ('pending', 'running', 'paused')"),
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    current_node: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[WorkflowRunStatus] = mapped_column(
        SQLAlchemyEnum(
            WorkflowRunStatus,
            name="workflow_run_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=WorkflowRunStatus.PENDING,
        nullable=False,
    )
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    workflow_type: Mapped[str] = mapped_column(
        String(50), default="chapter_revision", nullable=False
    )
    operation: Mapped[str] = mapped_column(String(50), default="generate", nullable=False)
    thread_id: Mapped[str] = mapped_column(
        String(64), default=lambda: str(uuid4()), unique=True, nullable=False
    )
    original_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflow_runs_original_version_id_chapter_versions",
        ),
        nullable=True,
    )
    current_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflow_runs_current_version_id_chapter_versions",
        ),
        nullable=True,
    )
    best_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflow_runs_best_version_id_chapter_versions",
        ),
        nullable=True,
    )
    accepted_version_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "chapter_versions.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_workflow_runs_accepted_version_id_chapter_versions",
        ),
        nullable=True,
    )
    revision_attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    max_revision_attempts: Mapped[int] = mapped_column(default=2, nullable=False)
    node_history: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    provider_call_count: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_estimated_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    provider_fallback_count: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_rate_limit_count: Mapped[int] = mapped_column(default=0, nullable=False)

    project: Mapped[Project] = relationship(back_populates="workflow_runs")
    chapter: Mapped[Chapter] = relationship(back_populates="workflow_runs")
    events: Mapped[list[WorkflowEvent]] = relationship(
        back_populates="workflow_run",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="WorkflowEvent.id",
    )


class WorkflowEvent(EntityBase):
    """One small, content-free audit event emitted at a workflow boundary."""

    __tablename__ = "workflow_events"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "node",
            "event_type",
            "attempt",
            name="workflow_event_idempotency",
        ),
        CheckConstraint("attempt >= 0", name="workflow_event_attempt_non_negative"),
        CheckConstraint("duration_ms >= 0", name="workflow_event_duration_non_negative"),
    )

    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    node: Mapped[str] = mapped_column(String(100), nullable=False)
    event_type: Mapped[WorkflowEventType] = mapped_column(
        SQLAlchemyEnum(
            WorkflowEventType,
            name="workflow_event_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(50), nullable=False)
    duration_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), nullable=True
    )
    evaluation_id: Mapped[int | None] = mapped_column(
        ForeignKey("evaluations.id", ondelete="SET NULL"), nullable=True
    )
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    workflow_run: Mapped[WorkflowRun] = relationship(back_populates="events")


class VersionComparison(EntityBase):
    """Persisted deterministic comparison between two chapter versions."""

    __tablename__ = "version_comparisons"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id", "new_version_id", name="version_comparison_workflow_new"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="comparison_confidence_range"),
    )

    workflow_run_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    old_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    new_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    dimensions: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    overall_delta: Mapped[float] = mapped_column(Float, nullable=False)
    resolved_issue_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    unresolved_issue_codes: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    newly_introduced_issue_codes: Mapped[list[str]] = mapped_column(
        JSON, default=list, nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class ProjectBudget(TimestampMixin, EntityBase):
    """Durable project-level cost limits and reservations."""

    __tablename__ = "project_budgets"
    __table_args__ = (
        UniqueConstraint("project_id", name="project_budget_project"),
        CheckConstraint("soft_limit >= 0", name="project_budget_soft_non_negative"),
        CheckConstraint("hard_limit > 0", name="project_budget_hard_positive"),
        CheckConstraint("soft_limit <= hard_limit", name="project_budget_limit_order"),
        CheckConstraint("spent_estimated >= 0", name="project_budget_estimated_non_negative"),
        CheckConstraint("spent_billed >= 0", name="project_budget_billed_non_negative"),
        CheckConstraint("reserved_estimated >= 0", name="project_budget_reserved_non_negative"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    soft_limit: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    hard_limit: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    period: Mapped[BudgetPeriod] = mapped_column(
        SQLAlchemyEnum(
            BudgetPeriod,
            name="budget_period",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=16,
        ),
        default=BudgetPeriod.LIFETIME,
        nullable=False,
    )
    spent_estimated: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    spent_billed: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    reserved_estimated: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    alert_thresholds: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ProviderCall(EntityBase):
    """Content-free audit row for one provider attempt."""

    __tablename__ = "provider_calls"
    __table_args__ = (
        UniqueConstraint(
            "idempotency_key",
            "attempt",
            "fallback_index",
            name="provider_call_attempt_identity",
        ),
        CheckConstraint("attempt > 0", name="provider_call_attempt_positive"),
        CheckConstraint("fallback_index >= 0", name="provider_call_fallback_non_negative"),
        CheckConstraint("input_tokens >= 0", name="provider_call_input_tokens_non_negative"),
        CheckConstraint("output_tokens >= 0", name="provider_call_output_tokens_non_negative"),
        CheckConstraint(
            "cached_input_tokens >= 0", name="provider_call_cached_tokens_non_negative"
        ),
        CheckConstraint("total_tokens >= 0", name="provider_call_total_tokens_non_negative"),
        CheckConstraint("latency_ms >= 0", name="provider_call_latency_non_negative"),
    )

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="SET NULL"), index=True, nullable=True
    )
    chapter_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="SET NULL"), index=True, nullable=True
    )
    task_type: Mapped[TaskType] = mapped_column(
        SQLAlchemyEnum(
            TaskType,
            name="provider_task_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        index=True,
        nullable=False,
    )
    provider: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    model: Mapped[str] = mapped_column(String(200), index=True, nullable=False)
    profile: Mapped[ModelProfile] = mapped_column(
        SQLAlchemyEnum(
            ModelProfile,
            name="provider_model_profile",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    privacy_policy: Mapped[PrivacyPolicy] = mapped_column(
        SQLAlchemyEnum(
            PrivacyPolicy,
            name="provider_privacy_policy",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    prompt_name: Mapped[str] = mapped_column(String(150), nullable=False)
    prompt_version: Mapped[str] = mapped_column(String(50), nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[ProviderCallStatus] = mapped_column(
        SQLAlchemyEnum(
            ProviderCallStatus,
            name="provider_call_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        index=True,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(nullable=False)
    fallback_index: Mapped[int] = mapped_column(default=0, nullable=False)
    fallback_reason: Mapped[str | None] = mapped_column(String(100), nullable=True)
    input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    output_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    cached_input_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    total_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    usage_source: Mapped[TokenUsageSource] = mapped_column(
        SQLAlchemyEnum(
            TokenUsageSource,
            name="token_usage_source",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=TokenUsageSource.UNKNOWN,
        nullable=False,
    )
    estimated_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    billed_cost: Mapped[Decimal | None] = mapped_column(Numeric(18, 8), nullable=True)
    currency: Mapped[str] = mapped_column(String(3), default="USD", nullable=False)
    pricing_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    latency_ms: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_request_id: Mapped[str | None] = mapped_column(String(200), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ProviderIdempotencyRecord(TimestampMixin, EntityBase):
    """Unique durable claim for a normalized provider request."""

    __tablename__ = "provider_idempotency_records"
    __table_args__ = (UniqueConstraint("idempotency_key", name="provider_idempotency_key"),)

    idempotency_key: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    status: Mapped[IdempotencyStatus] = mapped_column(
        SQLAlchemyEnum(
            IdempotencyStatus,
            name="provider_idempotency_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=16,
        ),
        default=IdempotencyStatus.ACTIVE,
        nullable=False,
    )
    provider_call_id: Mapped[int | None] = mapped_column(
        ForeignKey("provider_calls.id", ondelete="SET NULL"), nullable=True
    )
    response_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)


class Job(TimestampMixin, EntityBase):
    """PostgreSQL-authoritative asynchronous operation."""

    __tablename__ = "jobs"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="job_idempotency_key"),
        UniqueConstraint("workflow_run_id", name="job_workflow_run"),
        CheckConstraint("priority >= 0 AND priority <= 9", name="job_priority_range"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="job_progress_range"),
        CheckConstraint("attempt >= 0", name="job_attempt_non_negative"),
        CheckConstraint("max_attempts > 0", name="job_max_attempts_positive"),
        Index("ix_jobs_status_available_priority", "status", "available_at", "priority"),
        Index("ix_jobs_project_status", "project_id", "status"),
        Index("ix_jobs_chapter_status", "chapter_id", "status"),
        Index("ix_jobs_book_run_status", "book_run_id", "status"),
        Index("ix_jobs_lease_expires_at", "lease_expires_at"),
        Index(
            "uq_jobs_active_chapter",
            "chapter_id",
            unique=True,
            sqlite_where=text(
                "chapter_id IS NOT NULL AND status IN "
                "('pending','outbox_pending','queued','leased','running','pause_requested',"
                "'paused','cancel_requested','retry_scheduled')"
            ),
            postgresql_where=text(
                "chapter_id IS NOT NULL AND status IN "
                "('pending','outbox_pending','queued','leased','running','pause_requested',"
                "'paused','cancel_requested','retry_scheduled')"
            ),
        ),
    )

    project_id: Mapped[int | None] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=True
    )
    chapter_id: Mapped[int | None] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=True
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    book_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("book_runs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    parent_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), index=True, nullable=True
    )
    job_type: Mapped[JobType] = mapped_column(
        SQLAlchemyEnum(
            JobType,
            name="job_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        index=True,
        nullable=False,
    )
    queue_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(
            JobStatus,
            name="job_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=JobStatus.PENDING,
        index=True,
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(default=5, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    payload_schema_version: Mapped[int] = mapped_column(default=1, nullable=False)
    result: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    result_schema_version: Mapped[int] = mapped_column(default=1, nullable=False)
    progress: Mapped[int] = mapped_column(default=0, nullable=False)
    current_step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    max_attempts: Mapped[int] = mapped_column(default=3, nullable=False)
    event_sequence: Mapped[int] = mapped_column(default=0, server_default="0", nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    queued_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancel_requested_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    correlation_id: Mapped[str] = mapped_column(
        String(64), default=lambda: str(uuid4()), index=True, nullable=False
    )

    events: Mapped[list[JobEvent]] = relationship(
        back_populates="job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="JobEvent.id",
    )


class JobEvent(EntityBase):
    """Small durable progress event suitable for replay over SSE."""

    __tablename__ = "job_events"
    __table_args__ = (
        UniqueConstraint("job_id", "sequence", name="job_event_sequence"),
        CheckConstraint("progress >= 0 AND progress <= 100", name="job_event_progress_range"),
        CheckConstraint("attempt >= 0", name="job_event_attempt_non_negative"),
        Index("ix_job_events_job_id_id", "job_id", "id"),
    )

    job_id: Mapped[int] = mapped_column(
        ForeignKey("jobs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    sequence: Mapped[int] = mapped_column(nullable=False)
    event_type: Mapped[JobEventType] = mapped_column(
        SQLAlchemyEnum(
            JobEventType,
            name="job_event_type",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=40,
        ),
        nullable=False,
    )
    status: Mapped[JobStatus] = mapped_column(
        SQLAlchemyEnum(
            JobStatus,
            name="job_event_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    step: Mapped[str | None] = mapped_column(String(100), nullable=True)
    progress: Mapped[int] = mapped_column(default=0, nullable=False)
    message_code: Mapped[str] = mapped_column(String(100), nullable=False)
    message: Mapped[str] = mapped_column(String(500), nullable=False)
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    worker_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    workflow_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_events.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    job: Mapped[Job] = relationship(back_populates="events")


class OutboxMessage(EntityBase):
    """Transactional request for at-least-once broker publication."""

    __tablename__ = "outbox_messages"
    __table_args__ = (
        UniqueConstraint("deduplication_key", name="outbox_deduplication_key"),
        CheckConstraint("attempt >= 0", name="outbox_attempt_non_negative"),
        Index("ix_outbox_status_available", "status", "available_at"),
    )

    aggregate_type: Mapped[str] = mapped_column(String(50), nullable=False)
    aggregate_id: Mapped[int] = mapped_column(index=True, nullable=False)
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    status: Mapped[OutboxStatus] = mapped_column(
        SQLAlchemyEnum(
            OutboxStatus,
            name="outbox_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=16,
        ),
        default=OutboxStatus.PENDING,
        nullable=False,
    )
    attempt: Mapped[int] = mapped_column(default=0, nullable=False)
    available_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claimed_by: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    deduplication_key: Mapped[str] = mapped_column(String(100), nullable=False)


class WorkerRecord(EntityBase):
    """Persisted, secret-free worker heartbeat projection."""

    __tablename__ = "worker_records"
    __table_args__ = (UniqueConstraint("worker_id", name="worker_record_worker_id"),)

    worker_id: Mapped[str] = mapped_column(String(100), nullable=False)
    queue_name: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    status: Mapped[WorkerStatus] = mapped_column(
        SQLAlchemyEnum(
            WorkerStatus,
            name="worker_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=16,
        ),
        nullable=False,
    )
    current_job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    last_heartbeat_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    version: Mapped[str] = mapped_column(String(50), nullable=False)
