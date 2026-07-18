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


class MemoryStatus(StrEnum):
    """Visibility lifecycle shared by chunks and graph records."""

    CANDIDATE = "candidate"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"
    DELETED = "deleted"


class MemoryIndexStatus(StrEnum):
    """Synchronous indexing state retained for retry and audit."""

    PENDING = "pending"
    INDEXING = "indexing"
    COMPLETED = "completed"
    FAILED = "failed"
    SUPERSEDED = "superseded"


class GraphEntityType(StrEnum):
    """Controlled entity categories for the relational story graph."""

    CHARACTER = "character"
    LOCATION = "location"
    OBJECT = "object"
    EVENT = "event"
    SECRET = "secret"
    FACTION = "faction"
    RULE = "rule"
    FORESHADOWING = "foreshadowing"
    CHAPTER = "chapter"


class GraphPredicate(StrEnum):
    """Controlled graph edge predicates."""

    APPEARS_IN = "APPEARS_IN"
    LOCATED_AT = "LOCATED_AT"
    KNOWS = "KNOWS"
    OWNS = "OWNS"
    MEMBER_OF = "MEMBER_OF"
    CAUSED = "CAUSED"
    PARTICIPATED_IN = "PARTICIPATED_IN"
    FORESHADOWS = "FORESHADOWS"
    REVEALS = "REVEALS"
    CONFLICTS_WITH = "CONFLICTS_WITH"
    RELATED_TO = "RELATED_TO"


class TaskType(StrEnum):
    """Controlled model-routing tasks."""

    PLANNING = "planning"
    CHAPTER_DRAFTING = "chapter_drafting"
    FACT_EXTRACTION = "fact_extraction"
    GRAPH_EXTRACTION = "graph_extraction"
    LITERARY_CRITIQUE = "literary_critique"
    REVISION = "revision"
    VERSION_COMPARISON = "version_comparison"
    EMBEDDING_DOCUMENT = "embedding_document"
    EMBEDDING_QUERY = "embedding_query"


class ModelProfile(StrEnum):
    """Client-selectable, registry-backed model profiles."""

    OFFLINE = "offline"
    ECONOMY = "economy"
    BALANCED = "balanced"
    QUALITY = "quality"


class PrivacyPolicy(StrEnum):
    """Data-egress policy applied before provider calls."""

    OFFLINE = "offline"
    STRICT = "strict"
    STANDARD = "standard"


class ProviderCallStatus(StrEnum):
    """Durable provider-attempt state."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RATE_LIMITED = "rate_limited"
    TIMED_OUT = "timed_out"
    BUDGET_BLOCKED = "budget_blocked"
    CIRCUIT_OPEN = "circuit_open"
    CANCELLED = "cancelled"


class TokenUsageSource(StrEnum):
    """Provenance of token accounting."""

    PROVIDER_REPORTED = "provider_reported"
    LOCAL_ESTIMATE = "local_estimate"
    MOCK = "mock"
    UNKNOWN = "unknown"


class BudgetPeriod(StrEnum):
    """Supported project-budget reset periods."""

    LIFETIME = "lifetime"
    DAILY = "daily"
    MONTHLY = "monthly"


class IdempotencyStatus(StrEnum):
    """Durable ownership state for one normalized provider request."""

    ACTIVE = "active"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
