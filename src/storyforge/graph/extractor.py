"""Rule-first graph extraction from already validated accepted facts."""

from __future__ import annotations

from collections.abc import Sequence

from storyforge.enums import GraphEntityType, GraphPredicate
from storyforge.graph.models import (
    ExtractedGraphEntity,
    ExtractedGraphRelation,
    GraphExtractionResult,
)
from storyforge.models import Fact

_PREDICATES = {
    "located_at": GraphPredicate.LOCATED_AT,
    "is_at": GraphPredicate.LOCATED_AT,
    "location": GraphPredicate.LOCATED_AT,
    "owns": GraphPredicate.OWNS,
    "carries": GraphPredicate.OWNS,
    "possesses": GraphPredicate.OWNS,
    "knows": GraphPredicate.KNOWS,
    "learned": GraphPredicate.KNOWS,
    "discovered": GraphPredicate.KNOWS,
    "member_of": GraphPredicate.MEMBER_OF,
    "caused": GraphPredicate.CAUSED,
    "reveals": GraphPredicate.REVEALS,
}


class GraphExtractor:
    """Map Fact rows to controlled nodes and edges without another LLM call."""

    def __init__(self, *, minimum_confidence: float = 0.5) -> None:
        self.minimum_confidence = minimum_confidence

    def extract(
        self,
        facts: Sequence[Fact],
        *,
        chapter_number: int,
        content: str,
        character_names: set[str],
        location_names: set[str],
    ) -> GraphExtractionResult:
        entities: dict[tuple[GraphEntityType, str], ExtractedGraphEntity] = {}
        relations: list[ExtractedGraphRelation] = []
        for fact in facts:
            evidence = fact.source_quote.strip()
            if fact.confidence < self.minimum_confidence or not evidence or evidence not in content:
                continue
            subject_type = (
                GraphEntityType.CHARACTER
                if fact.subject in character_names
                else GraphEntityType.OBJECT
            )
            object_type = self._object_type(fact.object, location_names, fact.fact_type)
            if fact.subject.strip().casefold() == fact.object.strip().casefold():
                continue
            entities[(subject_type, fact.subject)] = ExtractedGraphEntity(
                entity_type=subject_type,
                canonical_name=fact.subject,
                confidence=fact.confidence,
                evidence=evidence[:500],
            )
            entities[(object_type, fact.object)] = ExtractedGraphEntity(
                entity_type=object_type,
                canonical_name=fact.object,
                confidence=fact.confidence,
                evidence=evidence[:500],
            )
            relations.append(
                ExtractedGraphRelation(
                    subject=fact.subject,
                    predicate=_PREDICATES.get(
                        fact.predicate.strip().casefold(), GraphPredicate.RELATED_TO
                    ),
                    object=fact.object,
                    confidence=fact.confidence,
                    evidence=evidence[:500],
                    valid_from_chapter=max(chapter_number, fact.valid_from_chapter),
                    valid_to_chapter=fact.valid_to_chapter,
                )
            )
        return GraphExtractionResult(
            entities=sorted(
                entities.values(), key=lambda item: (item.entity_type.value, item.canonical_name)
            ),
            relations=sorted(
                relations,
                key=lambda item: (item.subject, item.predicate.value, item.object, item.evidence),
            ),
        )

    @staticmethod
    def _object_type(value: str, location_names: set[str], fact_type: str) -> GraphEntityType:
        if value in location_names:
            return GraphEntityType.LOCATION
        if "secret" in fact_type.casefold() or "knowledge" in fact_type.casefold():
            return GraphEntityType.SECRET
        if "event" in fact_type.casefold() or "action" in fact_type.casefold():
            return GraphEntityType.EVENT
        return GraphEntityType.OBJECT
