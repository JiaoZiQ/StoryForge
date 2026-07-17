"""Embedding provider abstractions."""

from storyforge.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    EmbeddingError,
    EmbeddingInvalidResponseError,
    EmbeddingProvider,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
)
from storyforge.embeddings.factory import embedding_provider
from storyforge.embeddings.mock import MockEmbeddingProvider
from storyforge.embeddings.models import DATABASE_EMBEDDING_DIMENSIONS, MockEmbeddingFailure
from storyforge.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider

__all__ = [
    "DATABASE_EMBEDDING_DIMENSIONS",
    "EmbeddingConfigurationError",
    "EmbeddingDimensionError",
    "EmbeddingError",
    "EmbeddingInvalidResponseError",
    "EmbeddingProvider",
    "EmbeddingProviderError",
    "EmbeddingTimeoutError",
    "MockEmbeddingFailure",
    "MockEmbeddingProvider",
    "OpenAICompatibleEmbeddingProvider",
    "embedding_provider",
]
