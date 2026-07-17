"""OpenAI-compatible embedding provider with bounded retries and strict shape checks."""

from __future__ import annotations

import math
import time
from collections.abc import Callable, Sequence

import httpx
import openai
from openai import OpenAI
from pydantic import SecretStr

from storyforge.embeddings.base import (
    EmbeddingConfigurationError,
    EmbeddingDimensionError,
    EmbeddingInvalidResponseError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
)


class OpenAICompatibleEmbeddingProvider:
    """Batch text through the embeddings endpoint while preserving input order."""

    provider_name = "openai-compatible"

    def __init__(
        self,
        *,
        api_key: SecretStr,
        model: str,
        base_url: str,
        dimensions: int,
        batch_size: int,
        timeout_seconds: float,
        max_retries: int,
        http_client: httpx.Client | None = None,
        sleeper: Callable[[float], None] = time.sleep,
    ) -> None:
        if not api_key.get_secret_value() or not model.strip():
            raise EmbeddingConfigurationError("Embedding API key and model are required")
        try:
            endpoint = httpx.URL(base_url)
        except httpx.InvalidURL as exc:
            raise EmbeddingConfigurationError("Embedding base URL is invalid") from exc
        if endpoint.scheme not in {"http", "https"} or not endpoint.host or endpoint.userinfo:
            raise EmbeddingConfigurationError("Embedding base URL must be credential-free HTTP(S)")
        if dimensions < 2 or batch_size < 1 or timeout_seconds <= 0 or max_retries < 0:
            raise EmbeddingConfigurationError("Embedding numeric configuration is invalid")
        self._model = model
        self._dimensions = dimensions
        self._batch_size = batch_size
        self._max_retries = max_retries
        self._sleeper = sleeper
        try:
            self._client = OpenAI(
                api_key=api_key.get_secret_value(),
                base_url=base_url,
                timeout=timeout_seconds,
                max_retries=0,
                http_client=http_client,
            )
        except Exception as exc:
            raise EmbeddingConfigurationError("Could not initialize embedding provider") from exc

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def close(self) -> None:
        self._client.close()

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        if not texts:
            return []
        vectors: list[list[float]] = []
        for start in range(0, len(texts), self._batch_size):
            vectors.extend(self._request_batch(list(texts[start : start + self._batch_size])))
        if len(vectors) != len(texts):
            raise EmbeddingInvalidResponseError("Embedding response count did not match input")
        return vectors

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _request_batch(self, texts: list[str]) -> list[list[float]]:
        if any(not text.strip() for text in texts):
            raise EmbeddingProviderError("Embedding input must not be empty")
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.embeddings.create(
                    model=self._model,
                    input=texts,
                    dimensions=self._dimensions,
                )
                ordered = sorted(response.data, key=lambda item: item.index)
                if len(ordered) != len(texts):
                    raise EmbeddingInvalidResponseError(
                        "Embedding response count did not match input"
                    )
                vectors = [[float(value) for value in item.embedding] for item in ordered]
                for vector in vectors:
                    if len(vector) != self._dimensions or not all(map(math.isfinite, vector)):
                        raise EmbeddingDimensionError(
                            "Embedding response dimension did not match configuration"
                        )
                return vectors
            except EmbeddingInvalidResponseError:
                raise
            except openai.APITimeoutError as exc:
                if attempt >= self._max_retries:
                    raise EmbeddingTimeoutError("Embedding request timed out") from exc
            except (openai.AuthenticationError, openai.PermissionDeniedError) as exc:
                raise EmbeddingProviderError("Embedding credentials were rejected") from exc
            except openai.OpenAIError as exc:
                if attempt >= self._max_retries:
                    raise EmbeddingProviderError("Embedding provider request failed") from exc
            self._sleeper(0.5 * (2**attempt))
        raise EmbeddingProviderError("Embedding provider retries were exhausted")
