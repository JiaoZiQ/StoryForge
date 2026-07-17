"""Embedding provider contract and project-owned failures."""

from collections.abc import Sequence
from typing import Protocol

from storyforge.exceptions import StoryForgeError


class EmbeddingError(StoryForgeError):
    """Base class for sanitized embedding failures."""


class EmbeddingConfigurationError(EmbeddingError):
    """Raised for unsafe or incomplete embedding configuration."""


class EmbeddingProviderError(EmbeddingError):
    """Raised when an embedding endpoint cannot complete a request."""


class EmbeddingTimeoutError(EmbeddingProviderError):
    """Raised after the embedding timeout budget is exhausted."""


class EmbeddingInvalidResponseError(EmbeddingProviderError):
    """Raised when a provider returns the wrong count or shape."""


class EmbeddingDimensionError(EmbeddingInvalidResponseError):
    """Raised when a vector does not match the configured database dimension."""


class EmbeddingProvider(Protocol):
    """Text-only embedding boundary independent from the LLM provider."""

    @property
    def provider_name(self) -> str: ...

    @property
    def model_name(self) -> str: ...

    @property
    def dimensions(self) -> int: ...

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]: ...

    def embed_query(self, text: str) -> list[float]: ...
