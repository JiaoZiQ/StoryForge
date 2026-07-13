"""Central deterministic penalty and weighted-score calculations."""

from storyforge.evaluation.config import EvaluationScoringConfig
from storyforge.evaluation.models import (
    ChapterCritique,
    CombinedEvaluationResult,
    MechanicalIssue,
    RecommendedAction,
)


def bounded_score(value: float) -> float:
    """Clamp and round a score to the public 0..10 range."""
    return round(min(10.0, max(0.0, value)), 2)


def score_after_penalties(issues: list[MechanicalIssue]) -> float:
    """Apply all mechanical penalties in one centralized place."""
    return bounded_score(10.0 - sum(issue.score_penalty for issue in issues))


class EvaluationScorer:
    """Combine local and critic scores, then apply deterministic hard gates."""

    def __init__(self, config: EvaluationScoringConfig | None = None) -> None:
        self.config = config or EvaluationScoringConfig()

    def combine(
        self,
        *,
        mechanical_score: float,
        critique: ChapterCritique,
        consistency_score: float,
        critical_conflicts: int,
        high_conflicts: int,
        content_empty: bool,
    ) -> CombinedEvaluationResult:
        """Return raw/weighted scores, blocking reasons, and a recommendation."""
        raw_scores = {
            "mechanical": bounded_score(mechanical_score),
            "prose": critique.prose.score,
            "plot": critique.plot.score,
            "character": critique.character.score,
            "pacing": critique.pacing.score,
            "dialogue": critique.dialogue.score,
            "emotional_impact": critique.emotional_impact.score,
            "consistency": bounded_score(consistency_score),
            "outline_adherence": critique.outline_adherence.score,
            "critic_overall": critique.overall_score,
            "critic_consistency": critique.consistency.score,
        }
        weighted_scores = {
            name: round(raw_scores[name] * weight, 4)
            for name, weight in self.config.weights.items()
        }
        final_score = sum(weighted_scores.values())
        final_score -= high_conflicts * self.config.high_conflict_penalty
        if critical_conflicts:
            final_score = min(final_score, self.config.critical_score_cap)
        if content_empty:
            final_score = 0
        final_score = bounded_score(final_score)

        blocking_reasons: list[str] = []
        if content_empty:
            blocking_reasons.append("chapter_content_empty")
        if critical_conflicts:
            blocking_reasons.append("critical_conflict_present")
        if high_conflicts > self.config.max_high_conflicts:
            blocking_reasons.append("too_many_high_conflicts")
        if consistency_score < self.config.min_consistency_score:
            blocking_reasons.append("consistency_score_below_minimum")
        if critique.outline_adherence.score < self.config.min_outline_adherence_score:
            blocking_reasons.append("outline_adherence_below_minimum")
        if not critique.pass_recommendation:
            blocking_reasons.append("critic_does_not_recommend_pass")
        if final_score < self.config.pass_threshold:
            blocking_reasons.append("final_score_below_threshold")
        passed = not blocking_reasons
        if passed:
            action: RecommendedAction = "accept"
        elif content_empty or critical_conflicts > 1 or final_score < 3:
            action = "reject"
        elif critical_conflicts or high_conflicts > self.config.max_high_conflicts:
            action = "human_review"
        else:
            action = "revise"
        return CombinedEvaluationResult(
            final_score=final_score,
            passed=passed,
            raw_scores=raw_scores,
            weighted_scores=weighted_scores,
            blocking_reasons=blocking_reasons,
            recommended_action=action,
        )
