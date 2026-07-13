"""Typed models shared by mechanical, critic, scoring, and service boundaries."""

from typing import Annotated, Literal, Self

from pydantic import Field, model_validator

from storyforge.enums import ConflictSeverity, EvaluationStatus
from storyforge.schemas.base import EntityId, NonNegativeInt, PositiveInt, RequestModel

TenScore = Annotated[float, Field(ge=0, le=10)]
RecommendedAction = Literal["accept", "revise", "human_review", "reject"]


class MechanicalEvaluationRequest(RequestModel):
    """Input for deterministic local text checks."""

    chapter_id: EntityId
    chapter_number: PositiveInt
    content: str
    target_words: PositiveInt
    language: str = Field(default="zh-CN", min_length=2, max_length=32)


class MechanicalIssue(RequestModel):
    """One stable, explainable local quality issue."""

    code: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    severity: ConflictSeverity
    message: str = Field(min_length=1)
    evidence: str | None = Field(default=None, max_length=500)
    location: str | None = Field(default=None, max_length=100)
    score_penalty: float = Field(ge=0, le=10)


class MechanicalMetrics(RequestModel):
    """Deterministic text statistics used by local rules."""

    word_count: NonNegativeInt
    paragraph_count: NonNegativeInt
    sentence_count: NonNegativeInt
    average_sentence_length: float = Field(ge=0)
    sentence_length_stddev: float = Field(ge=0)
    dialogue_ratio: float = Field(ge=0, le=1)
    repeated_paragraph_count: NonNegativeInt
    repeated_ngram_ratio: float = Field(ge=0, le=1)
    banned_phrase_count: NonNegativeInt
    short_paragraph_ratio: float = Field(ge=0, le=1)
    long_paragraph_ratio: float = Field(ge=0, le=1)


class MechanicalEvaluationResult(RequestModel):
    """Complete deterministic evaluation result."""

    score: TenScore
    metrics: MechanicalMetrics
    issues: list[MechanicalIssue] = Field(default_factory=list)
    evaluator_version: str = Field(min_length=1, max_length=50)


class CriticIssue(RequestModel):
    """One structured literary or narrative issue from CriticAgent."""

    code: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=100)
    severity: ConflictSeverity
    description: str = Field(min_length=1)
    evidence: str | None = Field(default=None, max_length=500)
    suggestion: str = Field(min_length=1)
    affected_characters: list[str] = Field(default_factory=list)
    affected_facts: list[str] = Field(default_factory=list)


class DimensionScore(RequestModel):
    """A bounded critic dimension and concise rationale."""

    score: TenScore
    rationale: str = Field(min_length=1)


class ChapterCritique(RequestModel):
    """Strict structured output of CriticAgent."""

    prose: DimensionScore
    plot: DimensionScore
    character: DimensionScore
    pacing: DimensionScore
    dialogue: DimensionScore
    emotional_impact: DimensionScore
    consistency: DimensionScore
    outline_adherence: DimensionScore
    overall_score: TenScore
    strengths: list[str] = Field(default_factory=list)
    issues: list[CriticIssue] = Field(default_factory=list)
    revision_priorities: list[str] = Field(default_factory=list)
    pass_recommendation: bool

    @model_validator(mode="after")
    def validate_business_rules(self) -> Self:
        """Reject internally inconsistent critic recommendations."""
        dimensions = (
            self.prose,
            self.plot,
            self.character,
            self.pacing,
            self.dialogue,
            self.emotional_impact,
            self.consistency,
            self.outline_adherence,
        )
        mean_score = sum(item.score for item in dimensions) / len(dimensions)
        if abs(self.overall_score - mean_score) > 2:
            raise ValueError("overall_score is not reasonably aligned with dimension scores")
        issue_codes = [item.code for item in self.issues]
        if len(set(issue_codes)) != len(issue_codes):
            raise ValueError("critic issue codes must be unique")
        missing = set(self.revision_priorities) - set(issue_codes)
        if missing:
            raise ValueError("revision priorities must reference existing issue codes")
        critical_consistency = any(
            item.severity is ConflictSeverity.CRITICAL and item.category.casefold() == "consistency"
            for item in self.issues
        )
        if critical_consistency and self.pass_recommendation:
            raise ValueError("critical consistency issues cannot recommend passing")
        return self


class CriticCharacterContext(RequestModel):
    """Minimal writer-visible character data for literary critique."""

    name: str
    role: str
    description: str
    current_state: str


class CriticContext(RequestModel):
    """Explicit minimal context passed to CriticAgent."""

    project_id: EntityId
    chapter_id: EntityId
    chapter_number: PositiveInt
    genre: str
    premise: str
    outline: dict[str, object]
    content: str
    summary: str
    characters: list[CriticCharacterContext] = Field(default_factory=list)
    story_rules: list[str] = Field(default_factory=list)
    previous_chapter_summary: str | None = None
    active_foreshadowing: list[str] = Field(default_factory=list)
    mechanical_summary: dict[str, object]
    consistency_summary: dict[str, object]


class CombinedEvaluationResult(RequestModel):
    """Auditable deterministic score combination and gate decision."""

    final_score: TenScore
    passed: bool
    raw_scores: dict[str, TenScore]
    weighted_scores: dict[str, float]
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction


class ChapterEvaluationRequest(RequestModel):
    """Input for one immutable evaluation attempt."""

    project_id: EntityId
    chapter_number: PositiveInt


class ChapterEvaluationResult(RequestModel):
    """Persisted M4 evaluation result returned by the service."""

    evaluation_id: EntityId
    project_id: EntityId
    chapter_id: EntityId
    chapter_number: PositiveInt
    evaluation_version: PositiveInt
    status: EvaluationStatus
    mechanical_score: TenScore
    critic_score: TenScore
    consistency_score: TenScore
    final_score: TenScore
    passed: bool
    issue_count: NonNegativeInt
    conflict_count: NonNegativeInt
    critical_conflict_count: NonNegativeInt
    recommended_action: RecommendedAction
    blocking_reasons: list[str] = Field(default_factory=list)
    evaluator_versions: dict[str, str]
    prompt_versions: dict[str, str]
