"""Rule-first pairwise acceptance evaluation for chapter versions."""

from dataclasses import dataclass
from typing import Literal

from storyforge.revision.models import (
    ComparisonDecision,
    ComparisonDimension,
    EvaluationSnapshot,
    RevisionBrief,
    VersionComparisonResult,
)


@dataclass(frozen=True, slots=True)
class AcceptancePolicy:
    """Deterministic thresholds for comparing evaluated versions."""

    minimum_improvement: float = 0.25

    def __post_init__(self) -> None:
        if not 0 <= self.minimum_improvement <= 10:
            raise ValueError("minimum_improvement must be between 0 and 10")


class AcceptanceEvaluator:
    """Compare more than overall score and never accept a new critical conflict."""

    def __init__(self, policy: AcceptancePolicy | None = None) -> None:
        self.policy = policy or AcceptancePolicy()

    def compare(
        self,
        old: EvaluationSnapshot,
        new: EvaluationSnapshot,
        brief: RevisionBrief,
        *,
        revision_attempt: int,
        max_revision_attempts: int,
    ) -> VersionComparisonResult:
        """Return a deterministic pairwise decision and issue delta."""
        dimensions = [
            self._dimension("final_score", old.final_score, new.final_score),
            self._dimension("consistency", old.consistency_score, new.consistency_score),
            self._dimension(
                "outline_adherence",
                old.outline_adherence_score,
                new.outline_adherence_score,
            ),
        ]
        old_codes = set(old.issue_codes)
        new_codes = set(new.issue_codes)
        resolved = sorted(old_codes - new_codes)
        unresolved = sorted(old_codes & new_codes)
        introduced = sorted(new_codes - old_codes)
        delta = round(new.final_score - old.final_score, 3)
        at_limit = revision_attempt >= max_revision_attempts

        if new.critical_conflicts > old.critical_conflicts:
            decision: ComparisonDecision = "human_review" if at_limit else "keep_old_stop"
            rationale = "The revision introduced a new critical consistency conflict."
            confidence = 1.0
        elif new.passed and not new.blocking_reasons and new.critical_conflicts == 0:
            decision = "accept_new"
            rationale = "The revision satisfies every configured pass and blocking condition."
            confidence = 0.95
        elif at_limit:
            decision = "human_review"
            rationale = "The maximum revision attempts were reached without a passing version."
            confidence = 0.9
        elif (
            delta >= self.policy.minimum_improvement
            or new.critical_conflicts < old.critical_conflicts
            or len(new.blocking_reasons) < len(old.blocking_reasons)
        ):
            decision = "keep_old_retry"
            rationale = "The revision improved but still has blocking conditions."
            confidence = 0.8
        elif delta < -self.policy.minimum_improvement:
            decision = "keep_old_retry"
            rationale = "The revision is worse; retain the old best version and retry differently."
            confidence = 0.9
        else:
            decision = "keep_old_retry"
            rationale = "The change is below the minimum meaningful improvement threshold."
            confidence = 0.75

        requested_codes = {
            item.code for item in brief.instructions if item.severity.value in {"critical", "high"}
        }
        unresolved_requested = requested_codes & new_codes
        if decision == "accept_new" and unresolved_requested:
            decision = "keep_old_retry" if not at_limit else "human_review"
            rationale = "The revision passes scores but leaves requested revision tasks unresolved."
            confidence = 0.85

        return VersionComparisonResult(
            old_version_id=old.version_id,
            new_version_id=new.version_id,
            dimensions=dimensions,
            overall_delta=delta,
            resolved_issue_codes=resolved,
            unresolved_issue_codes=unresolved,
            newly_introduced_issue_codes=introduced,
            decision=decision,
            confidence=confidence,
            rationale=rationale,
        )

    @staticmethod
    def _dimension(name: str, old: float, new: float) -> ComparisonDimension:
        delta = round(new - old, 3)
        winner: Literal["old", "new", "tie"] = "new" if delta > 0 else "old" if delta < 0 else "tie"
        return ComparisonDimension(
            name=name,
            old_score=old,
            new_score=new,
            delta=delta,
            winner=winner,
            rationale=f"{name} changed by {delta:+.2f}.",
        )
