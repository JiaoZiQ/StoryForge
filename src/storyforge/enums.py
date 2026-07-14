"""Shared domain enumerations used by persistence and boundary schemas."""

from enum import StrEnum


class ProjectStatus(StrEnum):
    """Lifecycle status for a story project."""

    CREATED = "created"
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
    WORKFLOW_RUNNING = "workflow_running"
    DRAFTING = "drafting"
    REVISING = "revising"
    WORKFLOW_FAILED = "workflow_failed"


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
    PAUSED = "paused"
    COMPLETED = "completed"
    COMPLETED_NEEDS_REVIEW = "completed_needs_review"
    CANCELLED = "cancelled"


class ChapterVersionStatus(StrEnum):
    """Lifecycle of an immutable chapter text version."""

    DRAFT = "draft"
    EVALUATED = "evaluated"
    REVISION = "revision"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    NEEDS_REVIEW = "needs_review"


class FactStatus(StrEnum):
    """Promotion state for version-scoped extracted facts."""

    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class WorkflowEventType(StrEnum):
    """Auditable workflow event types."""

    NODE_STARTED = "node_started"
    NODE_COMPLETED = "node_completed"
    NODE_FAILED = "node_failed"
    ROUTE_SELECTED = "route_selected"
    VERSION_CREATED = "version_created"
    EVALUATION_CREATED = "evaluation_created"
    REVISION_REJECTED = "revision_rejected"
    VERSION_ACCEPTED = "version_accepted"
    WORKFLOW_COMPLETED = "workflow_completed"


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
