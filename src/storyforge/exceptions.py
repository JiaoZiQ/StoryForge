"""Stable application exceptions exposed above infrastructure boundaries."""


class StoryForgeError(Exception):
    """Base class for milestone-three application failures."""


class ConfigurationError(StoryForgeError):
    """Raised when application configuration is unsafe or incomplete."""


class DatabaseNotReadyError(StoryForgeError):
    """Raised when the database is reachable but has not reached migration head."""


class EntityNotFoundError(StoryForgeError):
    """Raised when a requested project or chapter does not exist."""


class InvalidStateError(StoryForgeError):
    """Raised when an operation is not allowed from the persisted state."""


class AlreadyExistsError(InvalidStateError):
    """Raised when an explicitly unique application resource already exists."""


class DatabaseConflictError(InvalidStateError):
    """Raised when persistence constraints reject a concurrent or duplicate write."""


class DomainValidationError(StoryForgeError):
    """Raised when typed input violates a cross-field domain rule."""


class WorkflowAlreadyRunningError(InvalidStateError):
    """Raised when a chapter already has an active durable workflow."""


class WorkflowNotResumableError(InvalidStateError):
    """Raised when a durable workflow cannot be resumed from its current state."""


class WorkflowCancelledError(InvalidStateError):
    """Raised when an operation targets a cancelled workflow."""


class PlanningValidationError(StoryForgeError):
    """Raised when planner output violates project invariants."""


class AgentExecutionError(StoryForgeError):
    """Raised when an LLM-backed agent cannot produce valid output."""


class ContextBuildError(StoryForgeError):
    """Raised when a valid chapter context cannot be assembled."""


class ChapterGenerationError(StoryForgeError):
    """Raised when chapter drafting or fact extraction fails."""


class EvaluationError(StoryForgeError):
    """Raised when a chapter evaluation cannot be completed safely."""


class WorkflowExecutionError(StoryForgeError):
    """Raised when a durable chapter workflow cannot continue safely."""


class ProviderGovernanceError(StoryForgeError):
    """Base class for policy decisions made before or around a provider call."""


class BudgetBlockedError(ProviderGovernanceError):
    """Raised before external work when a configured hard limit would be exceeded."""


class ProviderRateLimitError(ProviderGovernanceError):
    """Raised when the bounded process-local limiter cannot grant capacity."""


class CircuitOpenError(ProviderGovernanceError):
    """Raised when a provider/model circuit rejects a probe."""


class PrivacyPolicyError(ProviderGovernanceError):
    """Raised when configured data-egress policy forbids the provider call."""


class IdempotencyConflictError(ProviderGovernanceError):
    """Raised when an identical provider request is already active."""
