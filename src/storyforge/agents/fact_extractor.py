"""Fact extraction agent implementation and mechanical output filtering."""

from storyforge.agents.base import AgentResult, StructuredAgent
from storyforge.schemas.generation import FactExtractionRequest, FactExtractionResult


class FactExtractorAgent(StructuredAgent):
    """Extract quote-supported canonical updates from one generated chapter."""

    prompt_name = "fact_extractor"

    def extract(self, request: FactExtractionRequest) -> AgentResult[FactExtractionResult]:
        """Filter low-confidence, duplicate, future, or unsupported records."""
        result = self._invoke(request, FactExtractionResult)
        seen: set[tuple[str, str, str]] = set()
        facts = []
        for fact in result.output.facts:
            key = (
                fact.subject.casefold(),
                fact.predicate.casefold(),
                fact.object.casefold(),
            )
            if (
                fact.confidence < request.confidence_threshold
                or fact.source_quote not in request.chapter_content
                or fact.valid_from_chapter != request.chapter_number
                or key in seen
            ):
                continue
            seen.add(key)
            facts.append(fact)
        character_updates = [
            item
            for item in result.output.character_updates
            if item.confidence >= request.confidence_threshold
            and item.source_quote in request.chapter_content
        ]
        foreshadowing_updates = [
            item
            for item in result.output.foreshadowing_updates
            if item.confidence >= request.confidence_threshold
            and item.source_quote in request.chapter_content
        ]
        filtered = FactExtractionResult(
            facts=facts,
            character_updates=character_updates,
            foreshadowing_updates=foreshadowing_updates,
        )
        return AgentResult(
            output=filtered,
            provider=result.provider,
            model=result.model,
            prompt_versions=result.prompt_versions,
            attempts=result.attempts,
            duration_ms=result.duration_ms,
        )
