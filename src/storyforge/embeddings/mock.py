"""Stable hashing-vectorizer embeddings for offline development and tests."""

from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from collections import Counter, deque
from collections.abc import Iterable, Sequence

from storyforge.embeddings.base import (
    EmbeddingDimensionError,
    EmbeddingInvalidResponseError,
    EmbeddingProviderError,
    EmbeddingTimeoutError,
)
from storyforge.embeddings.models import DATABASE_EMBEDDING_DIMENSIONS, MockEmbeddingFailure

_TOKEN = re.compile(r"[a-z0-9]+|[\u3400-\u4dbf\u4e00-\u9fff]")


class MockEmbeddingProvider:
    """Produce normalized vectors using SHA-256 feature hashing, never ``hash()``."""

    provider_name = "mock"

    def __init__(
        self,
        *,
        dimensions: int = DATABASE_EMBEDDING_DIMENSIONS,
        model: str = "mock-hash-embedding-v1",
        failures: Iterable[MockEmbeddingFailure] = (),
    ) -> None:
        if dimensions < 2:
            raise EmbeddingDimensionError("Embedding dimensions must be at least two")
        self._dimensions = dimensions
        self._model = model
        self._failures = deque(failures)
        self.call_count = 0

    @property
    def model_name(self) -> str:
        return self._model

    @property
    def dimensions(self) -> int:
        return self._dimensions

    def embed_texts(self, texts: Sequence[str]) -> list[list[float]]:
        self.call_count += 1
        failure = self._failures.popleft() if self._failures else None
        if failure is MockEmbeddingFailure.TIMEOUT:
            raise EmbeddingTimeoutError("Mock embedding request timed out")
        if failure is MockEmbeddingFailure.INVALID_DIMENSION:
            raise EmbeddingDimensionError("Mock embedding returned an invalid dimension")
        if failure is MockEmbeddingFailure.EMPTY_RESPONSE:
            raise EmbeddingInvalidResponseError("Mock embedding returned no vectors")
        if failure is MockEmbeddingFailure.PARTIAL_FAILURE and len(texts) > 1:
            raise EmbeddingProviderError("Mock embedding batch partially failed")
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self.embed_texts([text])[0]

    def _embed(self, text: str) -> list[float]:
        normalized = " ".join(unicodedata.normalize("NFKC", text).casefold().split())
        if not normalized:
            raise EmbeddingProviderError("Embedding input must not be empty")
        compact = normalized.replace(" ", "")
        features = list(_TOKEN.findall(normalized))
        features.extend(compact[index : index + 3] for index in range(max(0, len(compact) - 2)))
        if not features:
            features = [normalized]
        vector = [0.0] * self._dimensions
        for feature, frequency in Counter(features).items():
            digest = hashlib.sha256(feature.encode("utf-8")).digest()
            index = int.from_bytes(digest[:8], "big") % self._dimensions
            sign = -1.0 if digest[8] & 1 else 1.0
            vector[index] += sign * (1.0 + math.log(float(frequency)))
        norm = math.sqrt(sum(value * value for value in vector))
        if norm == 0:
            raise EmbeddingProviderError("Embedding input produced an empty vector")
        return [value / norm for value in vector]
