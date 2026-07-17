"""Structured accepted-fact retrieval with chapter-time isolation."""

import re

from storyforge.database import SessionFactory
from storyforge.repositories import FactRepository
from storyforge.retrieval.models import HybridRetrievalRequest, RetrievalHit, RetrievalSource

_TERM = re.compile(r"[A-Za-z0-9_]+|[\u3400-\u4dbf\u4e00-\u9fff]{1,8}")


class FactRetriever:
    def __init__(self, session_factory: SessionFactory) -> None:
        self._session_factory = session_factory

    def retrieve(self, request: HybridRetrievalRequest) -> list[RetrievalHit]:
        if request.source_types and "fact" not in request.source_types:
            return []
        terms = list(dict.fromkeys(item.casefold() for item in _TERM.findall(request.query)))[:20]
        with self._session_factory() as session:
            facts = FactRepository(session).list_known_before(
                request.project_id, request.current_chapter
            )
            hits: list[RetrievalHit] = []
            for fact in facts:
                content = f"{fact.subject} {fact.predicate} {fact.object}"
                entity_filters = {
                    item.casefold() for item in (*request.character_names, *request.location_names)
                }
                fact_entities = {fact.subject.casefold(), fact.object.casefold()}
                if entity_filters and not entity_filters & fact_entities:
                    continue
                folded = content.casefold()
                matched = [term for term in terms if term in folded]
                if terms and not matched:
                    continue
                lexical = len(matched) / max(1, len(terms))
                score = min(1.0, 0.6 * fact.confidence + 0.4 * lexical)
                hits.append(
                    RetrievalHit(
                        id=fact.id,
                        source=RetrievalSource.FACT,
                        matched_sources=[RetrievalSource.FACT],
                        source_type="fact",
                        content=content,
                        score=score,
                        raw_score=fact.confidence,
                        project_id=fact.project_id,
                        chapter_number=fact.chapter.chapter_number,
                        version_id=fact.chapter_version_id,
                        entity_names=[fact.subject],
                        metadata={
                            "status": fact.status.value,
                            "normalized_hash": fact.normalized_hash,
                            "valid_from_chapter": fact.valid_from_chapter,
                        },
                        explanation=f"accepted fact confidence {fact.confidence:.3f}",
                    )
                )
        return sorted(hits, key=lambda item: (-item.score, item.id))[: request.top_k]
