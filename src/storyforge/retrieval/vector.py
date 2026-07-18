"""Real pgvector cosine retrieval with no SQLite masquerade."""

from collections.abc import Callable
from contextlib import AbstractContextManager

from storyforge.database import SessionFactory
from storyforge.embeddings import EmbeddingProvider
from storyforge.enums import TaskType
from storyforge.memory import MemoryChunkRepository
from storyforge.retrieval.models import (
    HybridRetrievalRequest,
    RetrievalHit,
    RetrievalSource,
    RetrieverUnavailableError,
)

ProviderFactory = Callable[[int, TaskType], AbstractContextManager[EmbeddingProvider]]


class VectorRetriever:
    def __init__(
        self,
        session_factory: SessionFactory,
        provider_factory: ProviderFactory,
        *,
        dimensions: int,
    ) -> None:
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._dimensions = dimensions

    def retrieve(self, request: HybridRetrievalRequest) -> list[RetrievalHit]:
        try:
            with self._provider_factory(request.project_id, TaskType.EMBEDDING_QUERY) as provider:
                vector = provider.embed_query(request.query)
        except Exception as exc:
            raise RetrieverUnavailableError("Vector embedding is unavailable") from exc
        if len(vector) != self._dimensions:
            raise RetrieverUnavailableError("Vector embedding dimension mismatch")
        try:
            with self._session_factory() as session:
                rows = MemoryChunkRepository(session).vector_candidates(
                    request.project_id,
                    current_chapter=request.current_chapter,
                    query_vector=vector,
                    source_types=request.source_types,
                    limit=request.top_k,
                )
                return [
                    RetrievalHit(
                        id=chunk.id,
                        source=RetrievalSource.VECTOR,
                        matched_sources=[RetrievalSource.VECTOR],
                        source_type=chunk.source_type,
                        content=chunk.content,
                        score=max(0.0, min(1.0, 1.0 - distance)),
                        raw_score=distance,
                        project_id=chunk.project_id,
                        chapter_number=chunk.valid_from_chapter,
                        version_id=chunk.chapter_version_id,
                        metadata={
                            "status": chunk.status.value,
                            "content_hash": chunk.content_hash,
                            "distance": distance,
                        },
                        explanation=f"pgvector cosine distance {distance:.6f}",
                    )
                    for chunk, distance in rows
                    if _matches_entities(request, chunk.details)
                ]
        except RuntimeError as exc:
            raise RetrieverUnavailableError("pgvector retrieval requires PostgreSQL") from exc


def _matches_entities(request: HybridRetrievalRequest, metadata: dict[str, object]) -> bool:
    filters = {item.casefold() for item in (*request.character_names, *request.location_names)}
    if not filters:
        return True
    raw_names = metadata.get("entity_names", [])
    if not isinstance(raw_names, list):
        return False
    names = {str(item).casefold() for item in raw_names}
    return bool(filters & names)
