"""Stable application exceptions exposed above infrastructure boundaries."""


class StoryForgeError(Exception):
    """Base class for milestone-three application failures."""


class EntityNotFoundError(StoryForgeError):
    """Raised when a requested project or chapter does not exist."""


class InvalidStateError(StoryForgeError):
    """Raised when an operation is not allowed from the persisted state."""


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
