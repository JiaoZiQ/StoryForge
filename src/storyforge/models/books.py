"""Persistence mappings for full-book generation and global evaluation."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import Enum as PythonEnum
from typing import Any
from uuid import uuid4

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
from sqlalchemy import Enum as SQLAlchemyEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storyforge.enums import (
    BookRevisionStatus,
    BookRunMode,
    BookRunStatus,
    BookSnapshotStatus,
    ChapterImpactStatus,
    KnowledgeStatus,
    ModelProfile,
    PrivacyPolicy,
)
from storyforge.models.base import EntityBase, TimestampMixin, utc_now


def _enum_values(enum_class: type[PythonEnum]) -> list[str]:
    return [str(member.value) for member in enum_class]


class BookRun(TimestampMixin, EntityBase):
    """PostgreSQL-authoritative execution state for one complete book run."""

    __tablename__ = "book_runs"
    __table_args__ = (
        CheckConstraint("total_chapters > 0", name="book_run_total_chapters_positive"),
        CheckConstraint("completed_chapters >= 0", name="book_run_completed_non_negative"),
        CheckConstraint("accepted_chapters >= 0", name="book_run_accepted_non_negative"),
        CheckConstraint("failed_chapters >= 0", name="book_run_failed_non_negative"),
        CheckConstraint("needs_review_chapters >= 0", name="book_run_review_non_negative"),
        CheckConstraint(
            "current_global_revision_round >= 0",
            name="book_run_revision_round_non_negative",
        ),
        CheckConstraint(
            "max_global_revision_rounds >= 0", name="book_run_max_revision_non_negative"
        ),
        CheckConstraint("progress >= 0 AND progress <= 100", name="book_run_progress_range"),
        Index(
            "uq_book_runs_active_project",
            "project_id",
            unique=True,
            sqlite_where=text(
                "status IN ('pending','planning_validation','generating','paused',"
                "'global_review','global_revision','cancel_requested','budget_blocked')"
            ),
            postgresql_where=text(
                "status IN ('pending','planning_validation','generating','paused',"
                "'global_review','global_revision','cancel_requested','budget_blocked')"
            ),
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    status: Mapped[BookRunStatus] = mapped_column(
        SQLAlchemyEnum(
            BookRunStatus,
            name="book_run_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=40,
        ),
        default=BookRunStatus.PENDING,
        nullable=False,
    )
    mode: Mapped[BookRunMode] = mapped_column(
        SQLAlchemyEnum(
            BookRunMode,
            name="book_run_mode",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=BookRunMode.SEQUENTIAL,
        nullable=False,
    )
    thread_id: Mapped[str] = mapped_column(
        String(36), unique=True, default=lambda: str(uuid4()), nullable=False
    )
    idempotency_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    total_chapters: Mapped[int] = mapped_column(nullable=False)
    completed_chapters: Mapped[int] = mapped_column(default=0, nullable=False)
    accepted_chapters: Mapped[int] = mapped_column(default=0, nullable=False)
    failed_chapters: Mapped[int] = mapped_column(default=0, nullable=False)
    needs_review_chapters: Mapped[int] = mapped_column(default=0, nullable=False)
    current_chapter_number: Mapped[int | None] = mapped_column(nullable=True)
    max_chapter_retries: Mapped[int] = mapped_column(default=2, nullable=False)
    max_global_revision_rounds: Mapped[int] = mapped_column(default=2, nullable=False)
    current_global_revision_round: Mapped[int] = mapped_column(default=0, nullable=False)
    model_profile: Mapped[ModelProfile] = mapped_column(
        SQLAlchemyEnum(
            ModelProfile,
            name="book_run_model_profile",
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
            name="book_run_privacy_policy",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        nullable=False,
    )
    budget_id: Mapped[int | None] = mapped_column(
        ForeignKey("project_budgets.id", ondelete="SET NULL"), nullable=True
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "jobs.id",
            ondelete="SET NULL",
            use_alter=True,
            name="fk_book_runs_job_id_jobs",
        ),
        unique=True,
        nullable=True,
    )
    workflow_run_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True
    )
    book_snapshot_id: Mapped[int | None] = mapped_column(nullable=True)
    best_snapshot_id: Mapped[int | None] = mapped_column(nullable=True)
    current_node: Mapped[str] = mapped_column(String(100), default="pending", nullable=False)
    node_history: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    chapter_job_map: Mapped[dict[str, int]] = mapped_column(JSON, default=dict, nullable=False)
    chapter_status_map: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    impacted_chapters: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    periodic_checks: Mapped[list[dict[str, Any]]] = mapped_column(
        JSON, default=list, nullable=False
    )
    progress: Mapped[int] = mapped_column(default=0, nullable=False)
    max_estimated_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    max_total_tokens: Mapped[int] = mapped_column(nullable=False)
    max_provider_calls: Mapped[int] = mapped_column(nullable=False)
    spent_cost: Mapped[Decimal] = mapped_column(
        Numeric(18, 8), default=Decimal("0"), nullable=False
    )
    used_tokens: Mapped[int] = mapped_column(default=0, nullable=False)
    provider_calls: Mapped[int] = mapped_column(default=0, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)

    snapshots: Mapped[list[BookSnapshot]] = relationship(
        back_populates="book_run",
        foreign_keys="BookSnapshot.book_run_id",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookSnapshot.snapshot_number",
    )


class BookSnapshot(EntityBase):
    """Immutable map from logical chapters to accepted or best text versions."""

    __tablename__ = "book_snapshots"
    __table_args__ = (
        UniqueConstraint("book_run_id", "snapshot_number", name="book_snapshot_run_number"),
        UniqueConstraint("book_run_id", "content_hash", name="book_snapshot_run_hash"),
        CheckConstraint("snapshot_number > 0", name="book_snapshot_number_positive"),
        CheckConstraint("chapter_count >= 0", name="book_snapshot_chapter_count_non_negative"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_run_id: Mapped[int] = mapped_column(
        ForeignKey("book_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    snapshot_number: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[BookSnapshotStatus] = mapped_column(
        SQLAlchemyEnum(
            BookSnapshotStatus,
            name="book_snapshot_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=BookSnapshotStatus.CANDIDATE,
        nullable=False,
    )
    chapter_version_map: Mapped[dict[str, int]] = mapped_column(JSON, nullable=False)
    total_words: Mapped[int] = mapped_column(default=0, nullable=False)
    chapter_count: Mapped[int] = mapped_column(default=0, nullable=False)
    accepted_chapter_count: Mapped[int] = mapped_column(default=0, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    evaluation_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    book_run: Mapped[BookRun] = relationship(back_populates="snapshots", foreign_keys=[book_run_id])


class TimelineEvent(EntityBase):
    """Deduplicated accepted-story event within a frozen book snapshot."""

    __tablename__ = "timeline_events"
    __table_args__ = (
        UniqueConstraint("book_snapshot_id", "event_key", name="timeline_snapshot_event_key"),
        CheckConstraint("sequence_index >= 0", name="timeline_sequence_non_negative"),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="timeline_confidence_range"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), index=True, nullable=False
    )
    event_key: Mapped[str] = mapped_column(String(64), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    story_time: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sequence_index: Mapped[int] = mapped_column(nullable=False)
    location_id: Mapped[int | None] = mapped_column(
        ForeignKey("locations.id", ondelete="SET NULL"), nullable=True
    )
    participant_entity_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    causes_event_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    consequence_event_ids: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)


class CharacterArcPoint(EntityBase):
    """One accepted, evidence-backed character state point."""

    __tablename__ = "character_arc_points"
    __table_args__ = (
        UniqueConstraint(
            "book_snapshot_id",
            "character_id",
            "chapter_number",
            name="character_arc_snapshot_character_chapter",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), nullable=False
    )
    goals: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    emotional_state: Mapped[str] = mapped_column(String(200), default="unknown", nullable=False)
    physical_state: Mapped[str] = mapped_column(String(200), default="unknown", nullable=False)
    location: Mapped[str | None] = mapped_column(String(200), nullable=True)
    relationships: Mapped[dict[str, str]] = mapped_column(JSON, default=dict, nullable=False)
    knowledge: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    conflicts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    decisions: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    evidence: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class CharacterKnowledge(EntityBase):
    """Explicit snapshot-scoped knowledge boundary for a character and accepted fact."""

    __tablename__ = "character_knowledge"
    __table_args__ = (
        UniqueConstraint(
            "book_snapshot_id", "character_id", "fact_id", name="knowledge_snapshot_character_fact"
        ),
        CheckConstraint("confidence >= 0 AND confidence <= 1", name="knowledge_confidence_range"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), index=True, nullable=False
    )
    fact_id: Mapped[int] = mapped_column(
        ForeignKey("facts.id", ondelete="CASCADE"), index=True, nullable=False
    )
    learned_chapter: Mapped[int] = mapped_column(nullable=False)
    source_event_id: Mapped[int | None] = mapped_column(
        ForeignKey("timeline_events.id", ondelete="SET NULL"), nullable=True
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    status: Mapped[KnowledgeStatus] = mapped_column(
        SQLAlchemyEnum(
            KnowledgeStatus,
            name="character_knowledge_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=KnowledgeStatus.KNOWN,
        nullable=False,
    )


class RelationshipHistory(EntityBase):
    """Versioned character relationship state with a chapter validity range."""

    __tablename__ = "relationship_history"
    __table_args__ = (
        UniqueConstraint(
            "book_snapshot_id",
            "subject_character_id",
            "object_character_id",
            "relationship_type",
            "valid_from_chapter",
            name="relationship_snapshot_pair_type_chapter",
        ),
        CheckConstraint(
            "valid_to_chapter IS NULL OR valid_to_chapter >= valid_from_chapter",
            name="relationship_valid_range",
        ),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    subject_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    object_character_id: Mapped[int] = mapped_column(
        ForeignKey("characters.id", ondelete="CASCADE"), nullable=False
    )
    relationship_type: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[str] = mapped_column(String(100), nullable=False)
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    chapter_version_id: Mapped[int] = mapped_column(
        ForeignKey("chapter_versions.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("timeline_events.id", ondelete="SET NULL"), nullable=True
    )
    valid_from_chapter: Mapped[int] = mapped_column(nullable=False)
    valid_to_chapter: Mapped[int | None] = mapped_column(nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="accepted", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, nullable=False)


class ChapterTransitionEvaluation(EntityBase):
    """Deterministic transition assessment for adjacent accepted chapters."""

    __tablename__ = "chapter_transition_evaluations"
    __table_args__ = (
        UniqueConstraint(
            "book_snapshot_id", "from_chapter", "to_chapter", name="transition_snapshot_pair"
        ),
        CheckConstraint("score >= 0 AND score <= 10", name="transition_score_range"),
    )

    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    from_chapter: Mapped[int] = mapped_column(nullable=False)
    to_chapter: Mapped[int] = mapped_column(nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    strengths: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)


class BookEvaluation(EntityBase):
    """Versioned global evaluation anchored to one immutable snapshot."""

    __tablename__ = "book_evaluations"
    __table_args__ = (
        UniqueConstraint("book_snapshot_id", "evaluation_version", name="book_eval_version"),
        UniqueConstraint("idempotency_key", name="book_eval_idempotency"),
        CheckConstraint("final_score >= 0 AND final_score <= 10", name="book_eval_score_range"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_run_id: Mapped[int] = mapped_column(
        ForeignKey("book_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), index=True, nullable=False
    )
    evaluation_version: Mapped[int] = mapped_column(nullable=False)
    final_score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    dimension_scores: Mapped[dict[str, float]] = mapped_column(JSON, nullable=False)
    blocking_reasons: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    recommended_action: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_chapters: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    global_issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list, nullable=False)
    critique: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)
    evaluator_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    prompt_versions: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(String(200), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )


class BookRevisionPlan(EntityBase):
    """Bounded deterministic plan for one global revision round."""

    __tablename__ = "book_revision_plans"
    __table_args__ = (
        UniqueConstraint("book_run_id", "revision_round", name="book_revision_run_round"),
        CheckConstraint("revision_round > 0", name="book_revision_round_positive"),
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_run_id: Mapped[int] = mapped_column(
        ForeignKey("book_runs.id", ondelete="CASCADE"), index=True, nullable=False
    )
    book_snapshot_id: Mapped[int] = mapped_column(
        ForeignKey("book_snapshots.id", ondelete="CASCADE"), nullable=False
    )
    revision_round: Mapped[int] = mapped_column(nullable=False)
    global_objectives: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dependency_order: Mapped[list[int]] = mapped_column(JSON, nullable=False)
    must_preserve: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    global_constraints: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    estimated_calls: Mapped[int] = mapped_column(nullable=False)
    estimated_tokens: Mapped[int] = mapped_column(nullable=False)
    estimated_cost: Mapped[Decimal] = mapped_column(Numeric(18, 8), nullable=False)
    status: Mapped[BookRevisionStatus] = mapped_column(
        SQLAlchemyEnum(
            BookRevisionStatus,
            name="book_revision_plan_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=BookRevisionStatus.PENDING,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )

    tasks: Mapped[list[BookRevisionTask]] = relationship(
        back_populates="plan",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="BookRevisionTask.dependency_order",
    )


class BookRevisionTask(EntityBase):
    """One chapter-scoped, bounded task within a global revision plan."""

    __tablename__ = "book_revision_tasks"
    __table_args__ = (
        UniqueConstraint("plan_id", "chapter_number", name="book_revision_task_plan_chapter"),
    )

    plan_id: Mapped[int] = mapped_column(
        ForeignKey("book_revision_plans.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_number: Mapped[int] = mapped_column(nullable=False)
    priority: Mapped[int] = mapped_column(nullable=False)
    issue_codes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    required_changes: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    preserve_facts: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    affected_future_chapters: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    rerun_global_checks: Mapped[list[str]] = mapped_column(JSON, nullable=False)
    dependency_order: Mapped[int] = mapped_column(nullable=False)
    impact_status: Mapped[ChapterImpactStatus] = mapped_column(
        SQLAlchemyEnum(
            ChapterImpactStatus,
            name="chapter_impact_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=ChapterImpactStatus.REVISION_REQUIRED,
        nullable=False,
    )
    status: Mapped[BookRevisionStatus] = mapped_column(
        SQLAlchemyEnum(
            BookRevisionStatus,
            name="book_revision_task_status",
            native_enum=False,
            create_constraint=True,
            values_callable=_enum_values,
            length=32,
        ),
        default=BookRevisionStatus.PENDING,
        nullable=False,
    )
    job_id: Mapped[int | None] = mapped_column(
        ForeignKey("jobs.id", ondelete="SET NULL"), nullable=True
    )

    plan: Mapped[BookRevisionPlan] = relationship(back_populates="tasks")
