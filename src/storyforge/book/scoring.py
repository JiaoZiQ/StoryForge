"""Deterministic global scoring with explicit non-score blockers."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.book.models import BookAnalysisBundle, BookCritique, BookEvaluationResult


class BookScoringConfig(BaseModel):
    """Validated global score weights and acceptance thresholds."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    weights: dict[str, float] = Field(
        default_factory=lambda: {
            "chapter_average": 0.15,
            "chapter_minimum": 0.10,
            "timeline": 0.15,
            "character_arcs": 0.10,
            "foreshadowing": 0.10,
            "pacing": 0.10,
            "transitions": 0.10,
            "repetition": 0.05,
            "book_critic": 0.15,
        }
    )
    pass_score: float = Field(default=7.0, ge=0, le=10)
    minimum_ending_score: float = Field(default=6.5, ge=0, le=10)
    minimum_character_arc_score: float = Field(default=6.0, ge=0, le=10)
    minimum_foreshadowing_payoff_rate: float = Field(default=0.6, ge=0, le=1)
    maximum_high_issues: int = Field(default=2, ge=0)

    @model_validator(mode="after")
    def validate_weights(self) -> BookScoringConfig:
        expected = {
            "chapter_average",
            "chapter_minimum",
            "timeline",
            "character_arcs",
            "foreshadowing",
            "pacing",
            "transitions",
            "repetition",
            "book_critic",
        }
        if set(self.weights) != expected or abs(sum(self.weights.values()) - 1.0) > 1e-9:
            raise ValueError("Book score weights must define every dimension and sum to one")
        return self


class BookEvaluationScorer:
    """Merge chapter, rules, and global critic scores without hiding blockers."""

    def __init__(self, config: BookScoringConfig | None = None) -> None:
        self.config = config or BookScoringConfig()

    def score(
        self,
        *,
        chapter_scores: list[float],
        ending_score: float,
        analysis: BookAnalysisBundle,
        critique: BookCritique,
    ) -> BookEvaluationResult:
        average = sum(chapter_scores) / len(chapter_scores) if chapter_scores else 0.0
        minimum = min(chapter_scores, default=0.0)
        transitions = (
            sum(item.score for item in analysis.transitions) / len(analysis.transitions)
            if analysis.transitions
            else 10.0
        )
        raw = {
            "chapter_average": round(average, 4),
            "chapter_minimum": round(minimum, 4),
            "timeline": analysis.timeline.score,
            "character_arcs": analysis.character_arcs.score,
            "foreshadowing": analysis.foreshadowing.score,
            "pacing": analysis.pacing.score,
            "transitions": round(transitions, 4),
            "repetition": analysis.repetition.score,
            "book_critic": critique.overall_score,
        }
        weighted = {
            name: round(value * self.config.weights[name], 4) for name, value in raw.items()
        }
        final = round(max(0.0, min(10.0, sum(weighted.values()))), 2)
        all_severities = [item.severity for item in analysis.timeline.conflicts]
        all_severities.extend(item.severity for item in analysis.character_arcs.issues)
        all_severities.extend(item.severity for item in analysis.foreshadowing.issues)
        all_severities.extend(item.severity for item in critique.global_issues)
        blockers: list[str] = []
        if not chapter_scores:
            blockers.append("No accepted chapter evaluations are available")
        if "critical" in all_severities:
            blockers.append("At least one critical global issue remains unresolved")
            final = min(final, 5.0)
        high_count = all_severities.count("high")
        if high_count > self.config.maximum_high_issues:
            blockers.append("Too many high-severity global issues remain unresolved")
        if ending_score < self.config.minimum_ending_score:
            blockers.append("The ending chapter is below the configured minimum score")
        if analysis.character_arcs.score < self.config.minimum_character_arc_score:
            blockers.append("Key character arcs are below the configured minimum score")
        if analysis.foreshadowing.payoff_rate < self.config.minimum_foreshadowing_payoff_rate:
            blockers.append("Important foreshadowing payoff rate is below the configured minimum")
        if not critique.pass_recommendation:
            blockers.append("The global critic does not recommend acceptance")
        passed = final >= self.config.pass_score and not blockers
        priority = sorted(
            {chapter for issue in critique.global_issues for chapter in issue.chapter_numbers}
            | {item.chapter_number for item in critique.chapter_priorities}
        )
        action: Literal["accept", "targeted_revision", "human_review", "reject"]
        if passed:
            action = "accept"
        elif priority:
            action = "targeted_revision"
        elif final < 4:
            action = "reject"
        else:
            action = "human_review"
        return BookEvaluationResult(
            final_score=final,
            passed=passed,
            dimension_scores=raw,
            weighted_scores=weighted,
            blocking_reasons=blockers,
            recommended_action=action,
            priority_chapters=priority,
        )
