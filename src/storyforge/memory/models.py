"""Typed memory indexing inputs and results."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class ChunkDraft(BaseModel):
    """One deterministic chunk before persistence and embedding."""

    model_config = ConfigDict(extra="forbid")

    chunk_index: int = Field(ge=0)
    content: str = Field(min_length=1)
    content_hash: str = Field(min_length=64, max_length=64)
    token_estimate: int = Field(ge=0)
    character_count: int = Field(ge=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemoryIndexResult(BaseModel):
    """Content-free result of one synchronous index operation."""

    project_id: int
    chapter_version_id: int
    status: Literal["completed", "failed"]
    chunk_count: int = Field(ge=0)
    graph_entity_count: int = Field(ge=0)
    graph_relation_count: int = Field(ge=0)
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int = Field(gt=0)
    degraded: bool = False


class MemoryIndexStatusResult(BaseModel):
    """Public index status without provider error details or content."""

    id: int
    project_id: int
    chapter_version_id: int
    status: str
    attempt_count: int
    chunk_count: int
    graph_entity_count: int
    graph_relation_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    error_code: str | None = None
