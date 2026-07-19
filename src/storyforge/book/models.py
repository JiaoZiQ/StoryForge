"""Typed data exchanged by full-book services and rule engines."""

from __future__ import annotations

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Severity = Literal["low", "medium", "high", "critical"]


class ChapterScheduleDecision(BaseModel):
    """The next safe chapter scheduling action."""

    chapter_number: int | None = Field(default=None, ge=1)
    action: Literal["schedule", "wait", "retry", "pause", "human_review", "complete", "cancel"]
    reason: str
    dependency_status: dict[int, str] = Field(default_factory=dict)


class SnapshotChapter(BaseModel):
    chapter_id: int
    chapter_number: int = Field(ge=1)
    chapter_version_id: int
    version: int = Field(ge=1)
    title: str
    summary: str
    word_count: int = Field(ge=0)
    content: str = Field(exclude=True)
    evaluation_score: float = Field(default=0, ge=0, le=10)
    outline_adherence: float = Field(default=0, ge=0, le=10)
    dialogue_ratio: float = Field(default=0, ge=0, le=1)
    key_events: list[str] = Field(default_factory=list)
    characters_present: list[str] = Field(default_factory=list)
    locations_present: list[str] = Field(default_factory=list)


class AcceptedFactData(BaseModel):
    id: int
    chapter_id: int
    chapter_version_id: int
    chapter_number: int = Field(ge=1)
    subject: str
    predicate: str
    object: str
    confidence: float = Field(ge=0, le=1)
    evidence: str
    valid_from_chapter: int = Field(ge=1)
    valid_to_chapter: int | None = Field(default=None, ge=1)


class CharacterProfileData(BaseModel):
    id: int
    name: str
    role: str
    goals: list[str] = Field(default_factory=list)
    personality: str
    current_state: str
    initial_knowledge: list[str] = Field(default_factory=list)


class TimelineEventData(BaseModel):
    event_key: str
    chapter_id: int
    chapter_version_id: int
    chapter_number: int = Field(ge=1)
    title: str
    description: str
    story_time: str | None = None
    sequence_index: int = Field(ge=0)
    location: str | None = None
    participants: list[str] = Field(default_factory=list)
    causes: list[str] = Field(default_factory=list)
    consequences: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0, le=1)
    evidence: str


class TimelineConflict(BaseModel):
    code: str
    severity: Severity
    chapter_numbers: list[int]
    event_keys: list[str]
    description: str
    evidence: list[str]
    suggested_resolution: str


class TimelineAnalysisResult(BaseModel):
    score: float = Field(ge=0, le=10)
    events: list[TimelineEventData]
    conflicts: list[TimelineConflict]
    checker_version: str = "timeline-rules-v1"


class CharacterArcPointData(BaseModel):
    character_id: int
    character_name: str
    chapter_number: int = Field(ge=1)
    chapter_version_id: int
    goals: list[str] = Field(default_factory=list)
    emotional_state: str = "unknown"
    physical_state: str = "unknown"
    location: str | None = None
    relationships: dict[str, str] = Field(default_factory=dict)
    knowledge: list[str] = Field(default_factory=list)
    conflicts: list[str] = Field(default_factory=list)
    decisions: list[str] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)


class CharacterArcIssue(BaseModel):
    code: str
    severity: Severity
    character_id: int
    character_name: str
    chapter_numbers: list[int]
    description: str
    evidence: list[str] = Field(default_factory=list)


class CharacterArcResult(BaseModel):
    score: float = Field(ge=0, le=10)
    points: list[CharacterArcPointData]
    issues: list[CharacterArcIssue]
    protagonist_coverage: float = Field(ge=0, le=1)


class KnowledgeBoundaryData(BaseModel):
    character_id: int
    character_name: str
    fact_id: int
    learned_chapter: int = Field(ge=1)
    source_event_key: str | None = None
    confidence: float = Field(ge=0, le=1)
    status: Literal["known", "forgotten", "misled", "false_belief"] = "known"


class RelationshipPointData(BaseModel):
    subject_character_id: int
    object_character_id: int
    relationship_type: Literal[
        "trust",
        "friendship",
        "hostility",
        "family",
        "romance",
        "alliance",
        "mentorship",
        "authority",
    ]
    value: str
    chapter_number: int = Field(ge=1)
    chapter_version_id: int
    evidence: str


class ForeshadowingItemData(BaseModel):
    id: int
    description: str
    importance: str
    setup_chapter: int = Field(ge=1)
    expected_payoff_chapter: int = Field(ge=1)
    payoff_chapter: int | None = Field(default=None, ge=1)
    status: str


class ForeshadowingIssue(BaseModel):
    code: str
    severity: Severity
    foreshadowing_id: int
    chapter_numbers: list[int]
    description: str
    evidence: list[str] = Field(default_factory=list)


class ForeshadowingAnalysisResult(BaseModel):
    score: float = Field(ge=0, le=10)
    total: int = Field(ge=0)
    setup_count: int = Field(ge=0)
    progressed_count: int = Field(ge=0)
    payoff_count: int = Field(ge=0)
    unresolved_count: int = Field(ge=0)
    early_payoff_count: int = Field(ge=0)
    repeated_payoff_count: int = Field(ge=0)
    overdue_count: int = Field(ge=0)
    no_setup_count: int = Field(ge=0)
    payoff_rate: float = Field(ge=0, le=1)
    average_setup_payoff_distance: float = Field(ge=0)
    issues: list[ForeshadowingIssue]


class TransitionIssue(BaseModel):
    code: str
    severity: Severity
    description: str
    evidence: str | None = None


class ChapterTransitionResult(BaseModel):
    from_chapter: int = Field(ge=1)
    to_chapter: int = Field(ge=1)
    score: float = Field(ge=0, le=10)
    issues: list[TransitionIssue]
    strengths: list[str]


class ChapterPacingMetrics(BaseModel):
    chapter_number: int = Field(ge=1)
    word_count: int = Field(ge=0)
    dialogue_ratio: float = Field(ge=0, le=1)
    action_ratio: float = Field(ge=0, le=1)
    description_ratio: float = Field(ge=0, le=1)
    conflict_intensity: float = Field(ge=0, le=10)
    information_reveals: int = Field(ge=0)
    new_characters: int = Field(ge=0)
    new_locations: int = Field(ge=0)
    foreshadowing_setups: int = Field(ge=0)
    foreshadowing_payoffs: int = Field(ge=0)
    chapter_score: float = Field(ge=0, le=10)
    emotional_intensity: float = Field(ge=0, le=10)
    ending_hook_strength: float = Field(ge=0, le=10)


class PacingIssue(BaseModel):
    code: str
    severity: Severity
    chapter_numbers: list[int]
    description: str


class PacingAnalysisResult(BaseModel):
    score: float = Field(ge=0, le=10)
    chapters: list[ChapterPacingMetrics]
    issues: list[PacingIssue]


class RepetitionCandidate(BaseModel):
    code: str
    severity: Severity
    chapter_numbers: list[int]
    similarity: float = Field(ge=0, le=1)
    evidence: list[str]
    legitimate_callback: bool = False


class RepetitionAnalysisResult(BaseModel):
    score: float = Field(ge=0, le=10)
    candidates: list[RepetitionCandidate]
    duplicate_paragraphs: int = Field(ge=0)
    repeated_phrase_count: int = Field(ge=0)


class BookIssue(BaseModel):
    code: str
    category: str
    severity: Severity
    description: str
    chapter_numbers: list[int] = Field(default_factory=list)
    evidence: list[str] = Field(default_factory=list)
    suggestion: str


class ChapterRevisionPriority(BaseModel):
    chapter_number: int = Field(ge=1)
    priority: int = Field(ge=1)
    issue_codes: list[str]
    objective: str


class DimensionScore(BaseModel):
    score: float = Field(ge=0, le=10)
    rationale: str


class BookCritique(BaseModel):
    model_config = ConfigDict(extra="forbid")

    premise_fulfillment: DimensionScore
    plot_coherence: DimensionScore
    character_arcs: DimensionScore
    pacing: DimensionScore
    world_consistency: DimensionScore
    thematic_coherence: DimensionScore
    foreshadowing: DimensionScore
    ending_quality: DimensionScore
    overall_score: float = Field(ge=0, le=10)
    strengths: list[str]
    global_issues: list[BookIssue]
    chapter_priorities: list[ChapterRevisionPriority]
    pass_recommendation: bool

    @model_validator(mode="after")
    def critical_issue_blocks_pass(self) -> BookCritique:
        if self.pass_recommendation and any(
            item.severity == "critical" for item in self.global_issues
        ):
            raise ValueError("A critical global issue cannot recommend passing")
        known = {item.code for item in self.global_issues}
        for priority in self.chapter_priorities:
            if not set(priority.issue_codes).issubset(known):
                raise ValueError("Chapter priority references an unknown global issue")
        return self


class BookCriticContext(BaseModel):
    """Compressed global-review input; full chapter bodies are intentionally absent."""

    project_title: str
    premise: str
    book_summary: str
    chapter_summaries: list[dict[str, str | int | float]]
    timeline_summary: dict[str, int | float | list[str]]
    character_arc_summary: dict[str, int | float | list[str]]
    relationship_summary: list[dict[str, str | int]]
    foreshadowing_summary: dict[str, int | float | list[str]]
    pacing_summary: dict[str, int | float | list[str]]
    transition_summary: dict[str, int | float | list[str]]
    repetition_summary: dict[str, int | float | list[str]]
    chapter_score_trend: list[float]
    priority_excerpt_summaries: list[dict[str, str | int]] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded_context(self) -> BookCriticContext:
        rendered = self.model_dump_json()
        if len(rendered) > 60_000:
            raise ValueError("Book critic context exceeds its compressed safety boundary")
        if len(self.priority_excerpt_summaries) > 8:
            raise ValueError("Book critic accepts at most eight priority excerpt summaries")
        return self


class BookAnalysisBundle(BaseModel):
    timeline: TimelineAnalysisResult
    character_arcs: CharacterArcResult
    knowledge: list[KnowledgeBoundaryData]
    relationships: list[RelationshipPointData]
    foreshadowing: ForeshadowingAnalysisResult
    transitions: list[ChapterTransitionResult]
    pacing: PacingAnalysisResult
    repetition: RepetitionAnalysisResult


class BookEvaluationResult(BaseModel):
    final_score: float = Field(ge=0, le=10)
    passed: bool
    dimension_scores: dict[str, float]
    weighted_scores: dict[str, float]
    blocking_reasons: list[str]
    recommended_action: Literal["accept", "targeted_revision", "human_review", "reject"]
    priority_chapters: list[int]


class ChapterRevisionTaskData(BaseModel):
    chapter_number: int = Field(ge=1)
    priority: int = Field(ge=1)
    issue_codes: list[str]
    objective: str
    required_changes: list[str]
    preserve_facts: list[str]
    affected_future_chapters: list[int]
    rerun_global_checks: list[str]


class BookRevisionPlanData(BaseModel):
    book_snapshot_id: int
    revision_round: int = Field(ge=1)
    global_objectives: list[str]
    chapter_tasks: list[ChapterRevisionTaskData]
    dependency_order: list[int]
    must_preserve: list[str]
    global_constraints: list[str]
    estimated_calls: int = Field(ge=0)
    estimated_tokens: int = Field(ge=0)
    estimated_cost: Decimal = Field(ge=0)
