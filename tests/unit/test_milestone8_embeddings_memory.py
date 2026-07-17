"""Deterministic embedding and chunking coverage for Milestone 8."""

from __future__ import annotations

import json
import math

import httpx
import pytest
from pydantic import SecretStr

from storyforge.embeddings import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    EmbeddingInvalidResponseError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
    MockEmbeddingFailure,
    MockEmbeddingProvider,
    OpenAICompatibleEmbeddingProvider,
)
from storyforge.memory import ChunkingConfig, MemoryChunker


def test_mock_embedding_is_stable_normalized_ordered_and_network_free() -> None:
    first = MockEmbeddingProvider(dimensions=64)
    second = MockEmbeddingProvider(dimensions=64)
    texts = ["Mara carries the brass key", "Mara holds a brass key", "the harbor moves"]
    vectors = first.embed_texts(texts)
    assert vectors == second.embed_texts(texts)
    assert vectors[0] != vectors[2]
    assert len(vectors) == 3
    assert all(len(vector) == 64 for vector in vectors)
    assert all(
        math.isclose(math.sqrt(sum(value * value for value in vector)), 1.0) for vector in vectors
    )
    assert first.embed_query(texts[0]) == vectors[0]


@pytest.mark.parametrize(
    ("failure", "error"),
    [
        (MockEmbeddingFailure.TIMEOUT, EmbeddingTimeoutError),
        (MockEmbeddingFailure.INVALID_DIMENSION, EmbeddingDimensionError),
        (MockEmbeddingFailure.EMPTY_RESPONSE, EmbeddingInvalidResponseError),
        (MockEmbeddingFailure.PARTIAL_FAILURE, EmbeddingProviderError),
    ],
)
def test_mock_embedding_failure_modes(
    failure: MockEmbeddingFailure, error: type[Exception]
) -> None:
    provider = MockEmbeddingProvider(dimensions=64, failures=[failure])
    with pytest.raises(error):
        provider.embed_texts(["one", "two"])


def test_mock_embedding_empty_input_and_invalid_content() -> None:
    provider = MockEmbeddingProvider(dimensions=64)
    assert provider.embed_texts([]) == []
    with pytest.raises(EmbeddingProviderError):
        provider.embed_query("  ")
    with pytest.raises(EmbeddingDimensionError):
        MockEmbeddingProvider(dimensions=1)


def test_openai_compatible_embedding_preserves_indexes_and_checks_dimensions() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path.endswith("/embeddings")
        assert body["model"] == "embed-test"
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "embed-test",
                "usage": {"prompt_tokens": 2, "total_tokens": 2},
                "data": [
                    {"object": "embedding", "index": 1, "embedding": [0.0, 1.0]},
                    {"object": "embedding", "index": 0, "embedding": [1.0, 0.0]},
                ],
            },
        )

    client = httpx.Client(transport=httpx.MockTransport(handler))
    provider = OpenAICompatibleEmbeddingProvider(
        api_key=SecretStr("test-key"),
        model="embed-test",
        base_url="https://embedding.invalid/v1",
        dimensions=2,
        batch_size=2,
        timeout_seconds=1,
        max_retries=0,
        http_client=client,
    )
    try:
        assert provider.embed_texts(["first", "second"]) == [[1.0, 0.0], [0.0, 1.0]]
        assert provider.provider_name == "openai-compatible"
        assert provider.model_name == "embed-test"
        assert provider.dimensions == 2
    finally:
        provider.close()


def test_openai_embedding_rejects_bad_shape_timeout_and_credentialed_url() -> None:
    def bad_shape(_: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "object": "list",
                "model": "embed-test",
                "usage": {"prompt_tokens": 1, "total_tokens": 1},
                "data": [{"object": "embedding", "index": 0, "embedding": [1.0]}],
            },
        )

    provider = OpenAICompatibleEmbeddingProvider(
        api_key=SecretStr("test-key"),
        model="embed-test",
        base_url="https://embedding.invalid/v1",
        dimensions=2,
        batch_size=2,
        timeout_seconds=1,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(bad_shape)),
    )
    try:
        with pytest.raises(EmbeddingDimensionError):
            provider.embed_query("text")
    finally:
        provider.close()

    def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    timed = OpenAICompatibleEmbeddingProvider(
        api_key=SecretStr("test-key"),
        model="embed-test",
        base_url="https://embedding.invalid/v1",
        dimensions=2,
        batch_size=2,
        timeout_seconds=1,
        max_retries=0,
        http_client=httpx.Client(transport=httpx.MockTransport(timeout)),
    )
    try:
        with pytest.raises(EmbeddingTimeoutError):
            timed.embed_query("text")
    finally:
        timed.close()
    with pytest.raises(EmbeddingConfigurationError, match="credential-free"):
        OpenAICompatibleEmbeddingProvider(
            api_key=SecretStr("test-key"),
            model="embed-test",
            base_url="https://user:secret@embedding.invalid/v1",
            dimensions=2,
            batch_size=2,
            timeout_seconds=1,
            max_retries=0,
        )


def test_chunker_is_structural_bounded_stable_and_overlapping() -> None:
    chunker = MemoryChunker(
        ChunkingConfig(target_chars=80, max_chars=100, overlap_chars=20, max_chunks_per_source=10)
    )
    content = (
        "# Arrival\n\nMara crossed the harbor. The clock struck midnight. "
        "She lifted the key.\n\n"
        "潮水退去。铜门打开。林舟记住了灯塔的位置。" * 3
    )
    first = chunker.chunk(content, source_type="chapter_content", language="mixed")
    second = chunker.chunk(content, source_type="chapter_content", language="mixed")
    assert first == second
    assert [item.chunk_index for item in first] == list(range(len(first)))
    assert all(item.character_count <= 100 for item in first)
    assert all(len(item.content_hash) == 64 for item in first)
    assert all(item.metadata["token_estimator"] == "char-cjk-v1" for item in first)
    assert "# Arrival" in first[0].content
    assert len(first) > 1
    assert chunker.chunk("", source_type="chapter_content") == []


def test_chunker_rejects_invalid_limits_and_chunk_explosion() -> None:
    with pytest.raises(ValueError, match="maximum"):
        ChunkingConfig(target_chars=100, max_chars=50)
    with pytest.raises(ValueError, match="overlap"):
        ChunkingConfig(target_chars=50, max_chars=100, overlap_chars=50)
    chunker = MemoryChunker(
        ChunkingConfig(target_chars=50, max_chars=50, overlap_chars=0, max_chunks_per_source=1)
    )
    with pytest.raises(ValueError, match="chunk limit"):
        chunker.chunk("A" * 120, source_type="chapter_content", language="en")
