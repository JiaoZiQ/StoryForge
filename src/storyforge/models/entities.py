"""SQLAlchemy 2 mappings for the StoryForge domain."""

from __future__ import annotations

from datetime import datetime
from enum import Enum as PythonEnum
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy import (
    Enum as SQLAlchemyEnum,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    ForeshadowingStatus,
    ProjectStatus,
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
        default=ProjectStatus.DRAFT,
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
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="ChapterVersion.version",
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

    project: Mapped[Project] = relationship(back_populates="facts")
    chapter: Mapped[Chapter] = relationship(back_populates="facts")
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )

    chapter: Mapped[Chapter] = relationship(back_populates="versions")


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
    )

    project_id: Mapped[int] = mapped_column(
        ForeignKey("projects.id", ondelete="CASCADE"), index=True, nullable=False
    )
    chapter_id: Mapped[int] = mapped_column(
        ForeignKey("chapters.id", ondelete="CASCADE"), index=True, nullable=False
    )
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
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utc_now, server_default=func.now(), nullable=False
    )
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    evaluation: Mapped[Evaluation] = relationship(back_populates="conflicts")
    project: Mapped[Project] = relationship(back_populates="conflicts")
    chapter: Mapped[Chapter] = relationship(back_populates="conflicts")
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
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="workflow_runs")
    chapter: Mapped[Chapter] = relationship(back_populates="workflow_runs")
