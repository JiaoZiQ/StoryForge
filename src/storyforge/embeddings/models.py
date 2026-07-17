"""Shared embedding constants and deterministic mock failure controls."""

from enum import StrEnum

DATABASE_EMBEDDING_DIMENSIONS = 64


class MockEmbeddingFailure(StrEnum):
    """One-shot failure injected into the offline provider."""

    TIMEOUT = "timeout"
    INVALID_DIMENSION = "invalid_dimension"
    EMPTY_RESPONSE = "empty_response"
    PARTIAL_FAILURE = "partial_failure"
