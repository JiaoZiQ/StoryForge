"""Deterministic relevance reranking with explicit factors."""

from collections.abc import Sequence
from dataclasses import dataclass

from storyforge.retrieval.models import HybridRetrievalRequest, RetrievalHit, RetrievalSource


@dataclass(frozen=True, slots=True)
class RerankerConfig:
    character_bonus: float = 0.08
    location_bonus: float = 0.07
    accepted_fact_bonus: float = 0.06
    story_rule_bonus: float = 0.05
    foreshadowing_bonus: float = 0.04
    trusted_source_bonus: float = 0.02
    multi_source_step: float = 0.03
    multi_source_cap: float = 0.10
    recency_cap: float = 0.05
    long_content_threshold: int = 1800
    long_content_penalty: float = 0.03


class Reranker:
    """Boost current entities, trusted facts, multi-source hits and recency."""

    def __init__(self, config: RerankerConfig | None = None) -> None:
        self.config = config or RerankerConfig()

    def rerank(
        self, request: HybridRetrievalRequest, hits: Sequence[RetrievalHit]
    ) -> list[RetrievalHit]:
        characters = {item.casefold() for item in request.character_names}
        locations = {item.casefold() for item in request.location_names}
        reranked: list[RetrievalHit] = []
        for hit in hits:
            factors: list[str] = []
            bonus = 0.0
            names = {item.casefold() for item in hit.entity_names}
            if names & characters:
                bonus += self.config.character_bonus
                factors.append("current_character")
            if names & locations:
                bonus += self.config.location_bonus
                factors.append("current_location")
            if RetrievalSource.FACT in hit.matched_sources:
                bonus += self.config.accepted_fact_bonus
                factors.append("accepted_fact")
            if hit.source_type == "story_rule":
                bonus += self.config.story_rule_bonus
                factors.append("active_rule")
            if hit.source_type == "foreshadowing":
                bonus += self.config.foreshadowing_bonus
                factors.append("active_foreshadowing")
            if hit.source_type in {"fact", "story_rule", "character", "location"}:
                bonus += self.config.trusted_source_bonus
                factors.append("trusted_source")
            if len(set(hit.matched_sources)) > 1:
                bonus += min(
                    self.config.multi_source_cap,
                    self.config.multi_source_step * (len(set(hit.matched_sources)) - 1),
                )
                factors.append("multi_source")
            if hit.chapter_number is not None:
                distance = max(1, request.current_chapter - hit.chapter_number)
                bonus += min(self.config.recency_cap, self.config.recency_cap / distance)
                factors.append("recency")
            if len(hit.content) > self.config.long_content_threshold:
                bonus -= self.config.long_content_penalty
                factors.append("length_penalty")
            reranked.append(
                hit.model_copy(
                    update={
                        "score": max(0.0, min(1.0, hit.score + bonus)),
                        "explanation": (f"{hit.explanation}; rerank={','.join(factors) or 'base'}"),
                    }
                )
            )
        return sorted(reranked, key=lambda item: (-item.score, item.source.value, item.id))
