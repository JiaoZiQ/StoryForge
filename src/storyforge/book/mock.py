"""Deterministic global-review response used by offline tests and demos."""

from storyforge.book.models import (
    BookCritique,
    ChapterRevisionPriority,
    DimensionScore,
)
from storyforge.llm import MockLLMProvider


def build_mock_book_critique(*, passing: bool = True) -> BookCritique:
    """Create a schema-valid whole-book critique without manuscript text or a network."""
    base = 8.2 if passing else 6.2
    return BookCritique(
        premise_fulfillment=DimensionScore(
            score=base, rationale="Chapter summaries advance the premise."
        ),
        plot_coherence=DimensionScore(
            score=base, rationale="Accepted events form a causal sequence."
        ),
        character_arcs=DimensionScore(
            score=base, rationale="Character state changes are evidence-backed."
        ),
        pacing=DimensionScore(
            score=base, rationale="Chapter metrics show a readable global shape."
        ),
        world_consistency=DimensionScore(
            score=base, rationale="Accepted facts respect declared rules."
        ),
        thematic_coherence=DimensionScore(score=base, rationale="Recurring themes remain visible."),
        foreshadowing=DimensionScore(
            score=base, rationale="Planned setups and payoffs are tracked."
        ),
        ending_quality=DimensionScore(
            score=base, rationale="The final chapter closes the central objective."
        ),
        overall_score=base,
        strengths=["The accepted chapter sequence has a stable causal spine."],
        global_issues=[],
        chapter_priorities=[],
        pass_recommendation=passing,
    )


def build_book_critic_provider(*, passing: bool = True) -> MockLLMProvider:
    provider = MockLLMProvider(model="mock-storyforge-v1")
    provider.register_response(BookCritique, build_mock_book_critique(passing=passing))
    return provider


__all__ = [
    "ChapterRevisionPriority",
    "build_book_critic_provider",
    "build_mock_book_critique",
]
