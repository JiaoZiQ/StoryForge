"""Unified, explainable hybrid retrieval contracts."""

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.exceptions import StoryForgeError


class RetrievalError(StoryForgeError):
    """Raised when retrieval cannot produce a trustworthy result."""


class RetrieverUnavailableError(RetrievalError):
    """Raised when one configured retrieval route is unavailable."""


class RetrievalSource(StrEnum):
    KEYWORD = "keyword"
    VECTOR = "vector"
    FACT = "fact"
    GRAPH = "graph"


class RetrievalHit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: int
    source: RetrievalSource
    matched_sources: list[RetrievalSource] = Field(default_factory=list)
    source_type: str
    content: str
    score: float = Field(ge=0, le=1)
    raw_score: float
    project_id: int
    chapter_number: int | None = None
    version_id: int | None = None
    entity_names: list[str] = Field(default_factory=list)
    relation_path: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    explanation: str


class HybridRetrievalRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project_id: int = Field(gt=0)
    query: str = Field(min_length=1, max_length=2000)
    current_chapter: int = Field(gt=0)
    character_names: list[str] = Field(default_factory=list)
    location_names: list[str] = Field(default_factory=list)
    source_types: list[str] = Field(default_factory=list)
    top_k: int = Field(default=20, ge=1, le=100)
    max_context_chars: int = Field(default=16_000, ge=100, le=100_000)
    include_sources: list[RetrievalSource] | None = None


class HybridRetrievalResult(BaseModel):
    query: str
    hits: list[RetrievalHit]
    total_candidates: int
    keyword_candidates: int
    vector_candidates: int
    fact_candidates: int
    graph_candidates: int
    deduplicated_count: int
    omitted_count: int
    estimated_chars: int
    retrieval_version: str
    filters_applied: list[str]
    degraded: bool = False
    degraded_reasons: list[str] = Field(default_factory=list)


class HybridWeights(BaseModel):
    keyword: float = Field(default=0.20, ge=0, le=1)
    vector: float = Field(default=0.35, ge=0, le=1)
    fact: float = Field(default=0.25, ge=0, le=1)
    graph: float = Field(default=0.20, ge=0, le=1)

    @model_validator(mode="after")
    def validate_total(self) -> "HybridWeights":
        if abs(self.keyword + self.vector + self.fact + self.graph - 1.0) > 1e-9:
            raise ValueError("Hybrid retrieval weights must sum to 1")
        return self


class RetrievalQueryPlan(BaseModel):
    semantic_query: str = Field(min_length=1, max_length=2000)
    keywords: list[str]
    character_names: list[str]
    location_names: list[str]
    relation_types: list[str]
    source_types: list[str]
