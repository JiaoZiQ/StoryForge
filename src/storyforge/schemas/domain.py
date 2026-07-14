"""Pydantic v2 request and response schemas for persisted domain entities."""

from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import ConfigDict, Field, model_validator

from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    ForeshadowingStatus,
    ProjectStatus,
    WorkflowRunStatus,
)
from storyforge.schemas.base import (
    CategoryText,
    Confidence,
    EntityId,
    LongText,
    NonNegativeInt,
    ORMResponseModel,
    PositiveInt,
    RequestModel,
    Score,
    ShortText,
)

CharacterName = Annotated[str, Field(min_length=1, max_length=150)]
OptionalScore = Annotated[float, Field(ge=0, le=100)] | None
M4Score = Annotated[float, Field(ge=0, le=10)]
RecommendedAction = Literal["accept", "revise", "human_review", "reject"]


class ProjectCreate(RequestModel):
    """Payload for creating a project."""

    title: ShortText
    genre: CategoryText
    premise: LongText
    target_chapters: PositiveInt
    target_words_per_chapter: PositiveInt
    language: str = Field(default="zh-CN", min_length=2, max_length=32)
    tone: CategoryText | None = None
    audience: CategoryText | None = None
    additional_requirements: str = Field(default="", max_length=10_000)
    status: ProjectStatus = ProjectStatus.CREATED


class ProjectUpdate(RequestModel):
    """Partial project update payload."""

    title: ShortText | None = None
    genre: CategoryText | None = None
    premise: LongText | None = None
    target_chapters: PositiveInt | None = None
    target_words_per_chapter: PositiveInt | None = None
    language: str | None = Field(default=None, min_length=2, max_length=32)
    tone: CategoryText | None = None
    audience: CategoryText | None = None
    additional_requirements: str | None = Field(default=None, max_length=10_000)
    status: ProjectStatus | None = None


class ProjectRead(ProjectCreate):
    """Project response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId
    logline: str | None = None
    themes: list[str] = Field(default_factory=list)
    world_summary: str | None = None
    central_conflict: str | None = None
    ending_direction: str | None = None
    style_guide: str | None = None
    created_at: datetime
    updated_at: datetime


class CharacterCreate(RequestModel):
    """Payload for creating a character."""

    project_id: EntityId
    name: CharacterName
    role: CategoryText
    description: LongText
    goals: list[LongText] = Field(default_factory=list)
    personality: LongText
    personality_traits: list[LongText] = Field(default_factory=list)
    speech_style: LongText
    current_state: LongText
    secrets: list[LongText] = Field(default_factory=list)
    knowledge: list[LongText] = Field(default_factory=list)


class CharacterUpdate(RequestModel):
    """Partial character update payload."""

    name: CharacterName | None = None
    role: CategoryText | None = None
    description: LongText | None = None
    goals: list[LongText] | None = None
    personality: LongText | None = None
    personality_traits: list[LongText] | None = None
    speech_style: LongText | None = None
    current_state: LongText | None = None
    secrets: list[LongText] | None = None
    knowledge: list[LongText] | None = None


class CharacterRead(CharacterCreate):
    """Character response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId


class LocationCreate(RequestModel):
    """Payload for creating a location."""

    project_id: EntityId
    name: CharacterName
    description: LongText
    rules: list[LongText] = Field(default_factory=list)


class LocationUpdate(RequestModel):
    """Partial location update payload."""

    name: CharacterName | None = None
    description: LongText | None = None
    rules: list[LongText] | None = None


class LocationRead(LocationCreate):
    """Location response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId


class StoryRuleCreate(RequestModel):
    """Payload for creating a story rule."""

    project_id: EntityId
    category: CategoryText
    statement: LongText
    source: ShortText
    active: bool = True
    structured_metadata: dict[str, object] = Field(default_factory=dict)


class StoryRuleUpdate(RequestModel):
    """Partial story-rule update payload."""

    category: CategoryText | None = None
    statement: LongText | None = None
    source: ShortText | None = None
    active: bool | None = None
    structured_metadata: dict[str, object] | None = None


class StoryRuleRead(StoryRuleCreate):
    """Story-rule response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId


class ChapterCreate(RequestModel):
    """Payload for creating a chapter."""

    project_id: EntityId
    chapter_number: PositiveInt
    title: ShortText
    outline: LongText
    content: str = ""
    summary: LongText | None = None
    status: ChapterStatus = ChapterStatus.PLANNED
    version: PositiveInt = 1
    score: OptionalScore = None


class ChapterUpdate(RequestModel):
    """Partial chapter update payload."""

    title: ShortText | None = None
    outline: LongText | None = None
    content: str | None = None
    summary: LongText | None = None
    status: ChapterStatus | None = None
    version: PositiveInt | None = None
    score: OptionalScore = None


class ChapterRead(ChapterCreate):
    """Chapter response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId
    created_at: datetime
    updated_at: datetime


class FactCreate(RequestModel):
    """Payload for creating a structured fact."""

    project_id: EntityId
    chapter_id: EntityId
    subject: ShortText
    predicate: ShortText
    object: LongText
    valid_from_chapter: PositiveInt
    valid_to_chapter: PositiveInt | None = None
    confidence: Confidence
    source_quote: LongText
    fact_type: str = Field(default="event", min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_chapter_range(self) -> Self:
        """Require an open or non-decreasing chapter-validity interval."""
        if self.valid_to_chapter is not None and self.valid_to_chapter < self.valid_from_chapter:
            raise ValueError("valid_to_chapter must be at least valid_from_chapter")
        return self


class FactUpdate(RequestModel):
    """Partial structured-fact update payload."""

    subject: ShortText | None = None
    predicate: ShortText | None = None
    object: LongText | None = None
    valid_from_chapter: PositiveInt | None = None
    valid_to_chapter: PositiveInt | None = None
    confidence: Confidence | None = None
    source_quote: LongText | None = None
    fact_type: str | None = Field(default=None, min_length=1, max_length=50)

    @model_validator(mode="after")
    def validate_complete_chapter_range(self) -> Self:
        """Validate the interval when both endpoints are present in one update."""
        if (
            self.valid_from_chapter is not None
            and self.valid_to_chapter is not None
            and self.valid_to_chapter < self.valid_from_chapter
        ):
            raise ValueError("valid_to_chapter must be at least valid_from_chapter")
        return self


class FactRead(FactCreate):
    """Structured-fact response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId


class ForeshadowingCreate(RequestModel):
    """Payload for creating a foreshadowing setup."""

    project_id: EntityId
    setup_chapter: PositiveInt
    expected_payoff_chapter: PositiveInt
    description: LongText
    status: ForeshadowingStatus = ForeshadowingStatus.PLANNED
    payoff_chapter: PositiveInt | None = None
    importance: str = Field(default="medium", pattern="^(low|medium|high)$")

    @model_validator(mode="after")
    def validate_payoff_ranges(self) -> Self:
        """Keep expected and actual payoff chapters after the setup."""
        if self.expected_payoff_chapter < self.setup_chapter:
            raise ValueError("expected_payoff_chapter must not precede setup_chapter")
        if self.payoff_chapter is not None and self.payoff_chapter < self.setup_chapter:
            raise ValueError("payoff_chapter must not precede setup_chapter")
        return self


class ForeshadowingUpdate(RequestModel):
    """Partial foreshadowing update payload."""

    expected_payoff_chapter: PositiveInt | None = None
    description: LongText | None = None
    status: ForeshadowingStatus | None = None
    payoff_chapter: PositiveInt | None = None
    importance: str | None = Field(default=None, pattern="^(low|medium|high)$")


class ForeshadowingRead(ForeshadowingCreate):
    """Foreshadowing response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId


class EvaluationCreate(RequestModel):
    """Payload for creating a structured evaluation."""

    project_id: EntityId
    chapter_id: EntityId
    evaluator: ShortText
    overall_score: Score
    consistency_score: Score
    prose_score: Score
    character_score: Score
    plot_score: Score
    issues: list[dict[str, object]] = Field(default_factory=list)
    suggestions: list[LongText] = Field(default_factory=list)
    evaluation_version: PositiveInt = 1
    status: EvaluationStatus = EvaluationStatus.COMPLETED
    mechanical_score: M4Score = 0
    critic_score: M4Score = 0
    pacing_score: M4Score = 0
    dialogue_score: M4Score = 0
    emotional_impact_score: M4Score = 0
    outline_adherence_score: M4Score = 0
    raw_scores: dict[str, float] = Field(default_factory=dict)
    weighted_scores: dict[str, float] = Field(default_factory=dict)
    mechanical_metrics: dict[str, object] = Field(default_factory=dict)
    critic_dimensions: dict[str, object] = Field(default_factory=dict)
    evaluator_versions: dict[str, str] = Field(default_factory=dict)
    prompt_versions: dict[str, str] = Field(default_factory=dict)
    blocking_reasons: list[str] = Field(default_factory=list)
    recommended_action: RecommendedAction = "human_review"
    passed: bool = False
    provider: str = "legacy"
    model: str = "legacy"
    config_version: str = "legacy"


class EvaluationUpdate(RequestModel):
    """Partial evaluation update payload."""

    evaluator: ShortText | None = None
    overall_score: Score | None = None
    consistency_score: Score | None = None
    prose_score: Score | None = None
    character_score: Score | None = None
    plot_score: Score | None = None
    issues: list[dict[str, object]] | None = None
    suggestions: list[LongText] | None = None
    status: EvaluationStatus | None = None
    mechanical_score: M4Score | None = None
    critic_score: M4Score | None = None
    pacing_score: M4Score | None = None
    dialogue_score: M4Score | None = None
    emotional_impact_score: M4Score | None = None
    outline_adherence_score: M4Score | None = None
    blocking_reasons: list[str] | None = None
    recommended_action: RecommendedAction | None = None
    passed: bool | None = None


class EvaluationRead(EvaluationCreate):
    """Evaluation response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId
    created_at: datetime


class EvaluationIssueRead(ORMResponseModel):
    """One persisted issue from a local or critic evaluator."""

    id: EntityId
    evaluation_id: EntityId
    source: str
    code: str
    category: str
    severity: ConflictSeverity
    description: str
    evidence: str | None = None
    suggestion: str | None = None
    score_penalty: M4Score
    details: dict[str, object] = Field(default_factory=dict)
    created_at: datetime


class ConflictRead(ORMResponseModel):
    """Persisted consistency conflict and its human-managed status."""

    id: EntityId
    evaluation_id: EntityId
    project_id: EntityId
    chapter_id: EntityId
    conflict_type: ConflictType
    severity: ConflictSeverity
    subject: str
    description: str
    new_evidence: str
    existing_evidence: str | None = None
    existing_fact_id: EntityId | None = None
    suggested_resolution: str
    confidence: Confidence
    rule_code: str
    status: ConflictStatus
    created_at: datetime
    resolved_at: datetime | None = None
    resolution_note: str | None = None


class ConflictStatusUpdate(RequestModel):
    """Only mutable field exposed for a consistency conflict."""

    status: ConflictStatus
    resolution_note: str | None = Field(default=None, max_length=2_000)


class RevisionCreate(RequestModel):
    """Payload for recording a chapter revision."""

    chapter_id: EntityId
    previous_version: PositiveInt
    new_version: PositiveInt
    reason: LongText
    score_before: Score
    score_after: Score
    accepted: bool = False

    @model_validator(mode="after")
    def validate_version_progression(self) -> Self:
        """Require the new version to advance from the previous version."""
        if self.new_version <= self.previous_version:
            raise ValueError("new_version must be greater than previous_version")
        return self


class RevisionUpdate(RequestModel):
    """Partial revision update payload."""

    previous_version: PositiveInt | None = None
    new_version: PositiveInt | None = None
    reason: LongText | None = None
    score_before: Score | None = None
    score_after: Score | None = None
    accepted: bool | None = None

    @model_validator(mode="after")
    def validate_complete_version_progression(self) -> Self:
        """Validate the version relation when both values are supplied."""
        if (
            self.previous_version is not None
            and self.new_version is not None
            and self.new_version <= self.previous_version
        ):
            raise ValueError("new_version must be greater than previous_version")
        return self


class RevisionRead(RevisionCreate):
    """Revision response model."""

    model_config = ConfigDict(from_attributes=True, str_strip_whitespace=True)

    id: EntityId
    created_at: datetime


class WorkflowRunCreate(RequestModel):
    """Payload for recording a workflow run."""

    project_id: EntityId
    chapter_id: EntityId
    current_node: CategoryText
    status: WorkflowRunStatus = WorkflowRunStatus.PENDING
    retry_count: NonNegativeInt = 0
    error_message: LongText | None = None
    started_at: datetime | None = None
    finished_at: datetime | None = None

    @model_validator(mode="after")
    def validate_timestamps(self) -> Self:
        """Prevent a supplied finish timestamp from preceding its supplied start."""
        if (
            self.started_at is not None
            and self.finished_at is not None
            and self.finished_at < self.started_at
        ):
            raise ValueError("finished_at must not precede started_at")
        return self


class WorkflowRunUpdate(RequestModel):
    """Partial workflow-run update payload."""

    current_node: CategoryText | None = None
    status: WorkflowRunStatus | None = None
    retry_count: NonNegativeInt | None = None
    error_message: LongText | None = None
    finished_at: datetime | None = None


class WorkflowRunRead(ORMResponseModel):
    """Workflow-run response model with a persisted start timestamp."""

    id: EntityId
    project_id: EntityId
    chapter_id: EntityId
    current_node: CategoryText
    status: WorkflowRunStatus
    retry_count: NonNegativeInt
    error_message: LongText | None
    started_at: datetime
    finished_at: datetime | None
