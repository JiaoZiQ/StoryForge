"""Content-free Milestone 8 demonstration projections."""

from typing import Literal

from pydantic import BaseModel, ConfigDict


class DemoM8Retrieval(BaseModel):
    keyword_candidates: int
    vector_candidates: int
    fact_candidates: int
    graph_candidates: int
    deduplicated_count: int
    final_hits: int


class DemoM8Context(BaseModel):
    included_memory_hits: int
    estimated_characters: int
    degraded_mode: bool


class DemoM8Isolation(BaseModel):
    candidate_chunks_visible: int
    rejected_chunks_visible: int
    superseded_chunks_visible: int
    future_chunks_visible: int


class DemoM8Duplicates(BaseModel):
    memory_chunks: int
    graph_entities: int
    graph_relations: int


class DemoM8Example(BaseModel):
    source_type: str
    sources: list[str]
    score: float
    explanation: str


class DemoM8Response(BaseModel):
    """Bounded summary proving real pgvector and hybrid retrieval behavior."""

    model_config = ConfigDict(extra="forbid")

    database_backend: Literal["PostgreSQL"]
    vector_extension: Literal["enabled"]
    embedding_provider: Literal["mock"]
    embedding_dimensions: int
    project_id: int
    workflow_status: str
    accepted_version: int
    revision_attempts: int
    memory_chunks: int
    graph_entities: int
    graph_relations: int
    retrieval: DemoM8Retrieval
    context: DemoM8Context
    isolation: DemoM8Isolation
    duplicates: DemoM8Duplicates
    reindex_attempts: int
    examples: list[DemoM8Example]
