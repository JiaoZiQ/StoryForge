"""Settings-backed embedding provider construction."""

from collections.abc import Iterator
from contextlib import contextmanager

from storyforge.embeddings.base import EmbeddingProvider
from storyforge.embeddings.mock import MockEmbeddingProvider
from storyforge.embeddings.openai_compatible import OpenAICompatibleEmbeddingProvider
from storyforge.settings import Settings


@contextmanager
def embedding_provider(settings: Settings) -> Iterator[EmbeddingProvider]:
    """Yield an independently configured embedding provider."""
    if settings.embedding_provider == "mock":
        yield MockEmbeddingProvider(
            dimensions=settings.embedding_dimensions,
            model=settings.embedding_model,
        )
        return
    key = settings.embedding_api_key
    if key is None:
        raise ValueError("Configured embedding provider has no API key")
    provider = OpenAICompatibleEmbeddingProvider(
        api_key=key,
        model=settings.embedding_model,
        base_url=settings.embedding_base_url,
        dimensions=settings.embedding_dimensions,
        batch_size=settings.embedding_batch_size,
        timeout_seconds=settings.embedding_timeout_seconds,
        max_retries=settings.embedding_max_retries,
    )
    try:
        yield provider
    finally:
        provider.close()
