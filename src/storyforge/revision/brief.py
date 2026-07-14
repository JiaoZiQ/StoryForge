"""Deterministic, bounded revision-brief construction."""

from dataclasses import dataclass

from storyforge.enums import ConflictSeverity
from storyforge.revision.models import RevisionBrief, RevisionInstruction, RevisionIssue

_SEVERITY_ORDER = {
    ConflictSeverity.CRITICAL: 0,
    ConflictSeverity.HIGH: 1,
    ConflictSeverity.MEDIUM: 2,
    ConflictSeverity.LOW: 3,
}
_CATEGORY_ORDER = {
    "consistency": 0,
    "forbidden_reveal": 1,
    "outline": 2,
    "character": 3,
    "plot": 4,
    "pacing": 5,
    "prose": 6,
    "mechanical": 7,
}


@dataclass(frozen=True, slots=True)
class RevisionBriefConfig:
    """Limits and default constraints for one revision round."""

    max_instructions: int = 5
    target_word_tolerance: float = 0.2

    def __post_init__(self) -> None:
        if not 3 <= self.max_instructions <= 5:
            raise ValueError("max_instructions must be between 3 and 5")
        if not 0 < self.target_word_tolerance < 1:
            raise ValueError("target_word_tolerance must be between 0 and 1")


class RevisionBriefBuilder:
    """Prioritize explainable issues without overwhelming RevisionAgent."""

    def __init__(self, config: RevisionBriefConfig | None = None) -> None:
        self.config = config or RevisionBriefConfig()

    def build(
        self,
        *,
        chapter_id: int,
        source_version_id: int,
        revision_attempt: int,
        objective: str,
        issues: list[RevisionIssue],
        must_preserve_facts: list[str],
        forbidden_changes: list[str],
        target_words: int,
        previous_improved: bool | None = None,
    ) -> RevisionBrief:
        """Return a stable priority-ordered brief for one attempt."""
        unique = {item.code: item for item in issues}
        ordered = sorted(
            unique.values(),
            key=lambda item: (
                _SEVERITY_ORDER[item.severity],
                _CATEGORY_ORDER.get(item.category.casefold(), 8),
                item.code,
            ),
        )[: self.config.max_instructions]
        strategy = "targeted_repair"
        if previous_improved is False:
            strategy = "structural_rewrite"
        elif revision_attempt > 1:
            strategy = "alternative_approach"
        instructions = [
            RevisionInstruction(
                priority=index,
                code=item.code,
                category=item.category,
                severity=item.severity,
                problem=item.problem,
                evidence=item.evidence,
                required_change=item.suggestion,
                preserve=list(must_preserve_facts[:3]),
                avoid=list(forbidden_changes),
                acceptance_criteria=[
                    f"Resolve issue {item.code}",
                    "Do not introduce a new high or critical consistency conflict",
                ],
            )
            for index, item in enumerate(ordered, start=1)
        ]
        tolerance = self.config.target_word_tolerance
        lower = max(1, round(target_words * (1 - tolerance)))
        upper = max(lower, round(target_words * (1 + tolerance)))
        return RevisionBrief(
            chapter_id=chapter_id,
            source_version_id=source_version_id,
            revision_attempt=revision_attempt,
            objective=objective
            or "Resolve blocking evaluation issues while preserving continuity.",
            instructions=instructions,
            global_constraints=[
                "Follow the current chapter outline and do not reveal future information.",
                "Preserve accepted facts unless an instruction explicitly corrects a conflict.",
                "Return a complete chapter, not notes or an outline.",
            ],
            must_preserve_facts=sorted(set(must_preserve_facts)),
            forbidden_changes=sorted(set(forbidden_changes)),
            target_word_range=(lower, upper),
            strategy=strategy,
        )
