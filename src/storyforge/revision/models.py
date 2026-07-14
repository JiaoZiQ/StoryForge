"""Typed revision and pairwise version-comparison boundaries."""

from typing import Annotated, Literal

from pydantic import Field

from storyforge.enums import ConflictSeverity
from storyforge.schemas.base import EntityId, PositiveInt, RequestModel

TenScore = Annotated[float, Field(ge=0, le=10)]
ComparisonDecision = Literal["accept_new", "keep_old_retry", "keep_old_stop", "human_review"]


class RevisionIssue(RequestModel):
    """Normalized issue input consumed by the rule-based brief builder."""

    code: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    severity: ConflictSeverity
    problem: str = Field(min_length=1)
    evidence: str | None = Field(default=None, max_length=500)
    suggestion: str = Field(min_length=1)
    source: Literal["consistency", "critic", "mechanical", "blocking"]


class RevisionInstruction(RequestModel):
    """One ordered, testable change requested from RevisionAgent."""

    priority: PositiveInt
    code: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    severity: ConflictSeverity
    problem: str = Field(min_length=1)
    evidence: str | None = Field(default=None, max_length=500)
    required_change: str = Field(min_length=1)
    preserve: list[str] = Field(default_factory=list)
    avoid: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)


class RevisionBrief(RequestModel):
    """Deterministic, bounded revision task for one source version."""

    chapter_id: EntityId
    source_version_id: EntityId
    revision_attempt: PositiveInt
    objective: str = Field(min_length=1)
    instructions: list[RevisionInstruction] = Field(default_factory=list)
    global_constraints: list[str] = Field(default_factory=list)
    must_preserve_facts: list[str] = Field(default_factory=list)
    forbidden_changes: list[str] = Field(default_factory=list)
    target_word_range: tuple[PositiveInt, PositiveInt]
    strategy: str = Field(min_length=1, max_length=100)


class RevisionAgentRequest(RequestModel):
    """Minimal, current-only context passed to RevisionAgent."""

    chapter_id: EntityId
    source_version_id: EntityId
    original_title: str
    original_content: str
    original_summary: str
    outline: dict[str, object]
    character_states: dict[str, str] = Field(default_factory=dict)
    story_rules: list[str] = Field(default_factory=list)
    accepted_facts: list[str] = Field(default_factory=list)
    active_foreshadowing: list[str] = Field(default_factory=list)
    style_guide: str = ""
    brief: RevisionBrief


class RevisedChapterDraft(RequestModel):
    """Strict structured output returned by RevisionAgent."""

    title: str = Field(min_length=1, max_length=200)
    content: str = Field(min_length=1)
    summary: str = Field(min_length=1)
    key_events: list[str] = Field(default_factory=list)
    characters_present: list[str] = Field(default_factory=list)
    locations_present: list[str] = Field(default_factory=list)
    changes_made: list[str] = Field(min_length=1)
    unresolved_items: list[str] = Field(default_factory=list)


class EvaluationSnapshot(RequestModel):
    """Small persisted-evaluation projection used for deterministic comparison."""

    evaluation_id: EntityId
    version_id: EntityId
    final_score: TenScore
    consistency_score: TenScore
    outline_adherence_score: TenScore
    critical_conflicts: int = Field(ge=0)
    high_conflicts: int = Field(ge=0)
    blocking_reasons: list[str] = Field(default_factory=list)
    issue_codes: list[str] = Field(default_factory=list)
    passed: bool
    recommended_action: Literal["accept", "revise", "human_review", "reject"]


class ComparisonDimension(RequestModel):
    """One auditable old/new score comparison."""

    name: str = Field(min_length=1, max_length=100)
    old_score: TenScore
    new_score: TenScore
    delta: float = Field(ge=-10, le=10)
    winner: Literal["old", "new", "tie"]
    rationale: str = Field(min_length=1)


class VersionComparisonResult(RequestModel):
    """Rule-first pairwise version decision persisted by the workflow."""

    old_version_id: EntityId
    new_version_id: EntityId
    dimensions: list[ComparisonDimension]
    overall_delta: float = Field(ge=-10, le=10)
    resolved_issue_codes: list[str] = Field(default_factory=list)
    unresolved_issue_codes: list[str] = Field(default_factory=list)
    newly_introduced_issue_codes: list[str] = Field(default_factory=list)
    decision: ComparisonDecision
    confidence: float = Field(ge=0, le=1)
    rationale: str = Field(min_length=1)
