"""Shared domain enumerations used by persistence and boundary schemas."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status for a story project."""

    DRAFT = "draft"
    PLANNING = "planning"
    PLANNED = "planned"
    GENERATING = "generating"
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"
    ARCHIVED = "archived"


class ChapterStatus(StrEnum):
    """Lifecycle status for a chapter."""

    PLANNED = "planned"
    GENERATING = "generating"
    DRAFT = "draft"
    EXTRACTING_FACTS = "extracting_facts"
    GENERATED = "generated"
    FACT_EXTRACTION_FAILED = "fact_extraction_failed"
    FAILED = "failed"
    EVALUATING = "evaluating"
    EVALUATED_PASSED = "evaluated_passed"
    EVALUATED_NEEDS_REVISION = "evaluated_needs_revision"
    EVALUATION_FAILED = "evaluation_failed"
    NEEDS_REVISION = "needs_revision"
    ACCEPTED = "accepted"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ForeshadowingStatus(StrEnum):
    """Lifecycle status for a foreshadowing setup."""

    PLANNED = "planned"
    OPEN = "open"
    RESOLVED = "resolved"
    ABANDONED = "abandoned"


class WorkflowRunStatus(StrEnum):
    """Execution status for a persisted workflow run."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    NEEDS_HUMAN_REVIEW = "needs_human_review"


class ConflictType(StrEnum):
    """Mechanically explainable consistency-conflict categories."""

    CHARACTER_STATE = "character_state"
    CHARACTER_KNOWLEDGE = "character_knowledge"
    CHARACTER_EXISTENCE = "character_existence"
    LOCATION = "location"
    TIMELINE = "timeline"
    OBJECT_STATE = "object_state"
    STORY_RULE = "story_rule"
    FACT_CONTRADICTION = "fact_contradiction"
    FORESHADOWING = "foreshadowing"
    OUTLINE_VIOLATION = "outline_violation"


class ConflictSeverity(StrEnum):
    """Severity shared by consistency and evaluation issues."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ConflictStatus(StrEnum):
    """Human-managed lifecycle of a persisted conflict."""

    OPEN = "open"
    IGNORED = "ignored"
    RESOLVED = "resolved"
    FALSE_POSITIVE = "false_positive"


class EvaluationStatus(StrEnum):
    """Durability status of one evaluation attempt."""

    COMPLETED = "completed"
    PARTIAL_FAILED = "partial_failed"
