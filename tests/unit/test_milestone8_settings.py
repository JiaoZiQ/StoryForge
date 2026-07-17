"""Embedding and hybrid retrieval settings fail fast and remain independent."""

import pytest

from storyforge.exceptions import ConfigurationError
from storyforge.settings import Settings


def test_embedding_and_llm_provider_configuration_are_independent() -> None:
    settings = Settings(
        environment="test",
        database_url="sqlite://",
        llm_provider="mock",
        embedding_provider="openai-compatible",
        embedding_model="embed-model",
        embedding_api_key="embedding-only-key",
    )
    assert settings.llm_api_key is None
    assert settings.embedding_api_key is not None
    assert settings.embedding_api_key.get_secret_value() == "embedding-only-key"
    assert "embedding-only-key" not in repr(settings)


def test_embedding_dimensions_weights_and_limits_fail_early() -> None:
    with pytest.raises(ConfigurationError, match="database dimension"):
        Settings(embedding_dimensions=32)
    with pytest.raises(ConfigurationError, match="sum"):
        Settings(hybrid_keyword_weight=0.5)
    with pytest.raises(ConfigurationError, match="maximum"):
        Settings(retrieval_top_k=20, retrieval_max_top_k=10)


def test_production_requires_real_embedding_configuration_without_mock_fallback() -> None:
    with pytest.raises(ConfigurationError, match="embedding provider"):
        Settings(
            environment="production",
            database_url="postgresql://storyforge:unique@db/storyforge",
            llm_provider="openai-compatible",
            llm_model="structured-model",
            llm_api_key="llm-key",
            mock_mode=False,
        )
    with pytest.raises(ConfigurationError, match="embedding provider requires an API key"):
        Settings(
            environment="production",
            database_url="postgresql://storyforge:unique@db/storyforge",
            llm_provider="openai-compatible",
            llm_model="structured-model",
            llm_api_key="llm-key",
            embedding_provider="openai-compatible",
            embedding_model="embed-model",
            mock_mode=False,
        )
