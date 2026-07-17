"""Deterministic PostgreSQL/SQLite keyword retrieval over accepted memory."""

import re

from storyforge.database import SessionFactory
from storyforge.memory import MemoryChunkRepository
from storyforge.retrieval.models import HybridRetrievalRequest, RetrievalHit, RetrievalSource

_TERM = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]{1,8}")


class KeywordRetriever:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def retrieve(self, request: HybridRetrievalRequest) -> list[RetrievalHit]:
        terms = list(dict.fromkeys(item.casefold() for item in _TERM.findall(request.query)))[:20]
        with self._session_factory() as session:
            chunks = MemoryChunkRepository(session).keyword_candidates(
                request.project_id,
                current_chapter=request.current_chapter,
                terms=terms,
                source_types=request.source_types,
                limit=min(request.top_k * 4, 100),
            )
            hits = []
            for chunk in chunks:
                if not _matches_entities(request, chunk.details):
                    continue
                folded = chunk.content.casefold()
                matched = [term for term in terms if term in folded]
                score = min(1.0, len(matched) / max(1, len(terms)))
                hits.append(
                    RetrievalHit(
                        id=chunk.id,
                        source=RetrievalSource.KEYWORD,
                        matched_sources=[RetrievalSource.KEYWORD],
                        source_type=chunk.source_type,
                        content=chunk.content,
                        score=score,
                        raw_score=float(len(matched)),
                        project_id=chunk.project_id,
                        chapter_number=chunk.valid_from_chapter,
                        version_id=chunk.chapter_version_id,
                        metadata={
                            "status": chunk.status.value,
                            "content_hash": chunk.content_hash,
                            "matched_terms": matched,
                        },
                        explanation=f"keyword match: {', '.join(matched[:5])}",
                    )
                )
        return sorted(hits, key=lambda item: (-item.score, item.id))[: request.top_k]


def _matches_entities(request: HybridRetrievalRequest, metadata: dict[str, object]) -> bool:
    filters = {item.casefold() for item in (*request.character_names, *request.location_names)}
    if not filters:
        return True
    raw_names = metadata.get("entity_names", [])
    if not isinstance(raw_names, list):
        return False
    names = {str(item).casefold() for item in raw_names}
    return bool(filters & names)
