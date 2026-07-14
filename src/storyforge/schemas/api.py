"""Stable API and CLI boundary models for Milestone 6."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.enums import (
    ChapterStatus,
    ChapterVersionStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    FactStatus,
    ProjectStatus,
    WorkflowEventType,
    WorkflowRunStatus,
)
from storyforge.schemas.base import RequestModel

EntityId = Annotated[int, Field(gt=0)]
PageNumber = Annotated[int, Field(ge=1)]
PageSize = Annotated[int, Field(ge=1, le=100)]
TenScore = Annotated[float, Field(ge=0, le=10)]
SortOrder = Literal["asc", "desc"]


class PageMeta(BaseModel):
    page: int
    page_size: int
    total_items: int
    total_pages: int


class ErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
    context: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class ErrorResponse(BaseModel):
    error: str
    message: str
    details: list[ErrorDetail] = Field(default_factory=list)
    request_id: str | None = None


class PageResponse[ItemT](BaseModel):
    items: list[ItemT]
    meta: PageMeta


class ProjectCreateRequest(RequestModel):
    title: str = Field(min_length=1, max_length=200)
    genre: str = Field(min_length=1, max_length=100)
    premise: str = Field(min_length=1, max_length=20_000)
    target_chapters: int = Field(ge=1, le=1_000)
    target_words_per_chapter: int = Field(ge=50, le=100_000)
    language: str = Field(default="zh-CN", min_length=2, max_length=32)
    tone: str | None = Field(default=None, min_length=1, max_length=100)
    audience: str | None = Field(default=None, min_length=1, max_length=100)
    additional_requirements: str = Field(default="", max_length=10_000)


class ProjectUpdateRequest(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    genre: str | None = Field(default=None, min_length=1, max_length=100)
    premise: str | None = Field(default=None, min_length=1, max_length=20_000)
    target_chapters: int | None = Field(default=None, ge=1, le=1_000)
    target_words_per_chapter: int | None = Field(default=None, ge=50, le=100_000)
    language: str | None = Field(default=None, min_length=2, max_length=32)
    tone: str | None = Field(default=None, min_length=1, max_length=100)
    audience: str | None = Field(default=None, min_length=1, max_length=100)
    additional_requirements: str | None = Field(default=None, max_length=10_000)


class ProjectSummary(BaseModel):
    id: int
    title: str
    genre: str
    language: str
    status: ProjectStatus
    target_chapters: int
    target_words_per_chapter: int
    created_at: datetime
    updated_at: datetime


class ProjectDetail(ProjectSummary):
    premise: str
    tone: str | None
    audience: str | None
    additional_requirements: str
    logline: str | None
    themes: list[str]
    world_summary: str | None
    central_conflict: str | None
    style_guide: str | None
    chapter_count: int
    workflow_count: int


class GeneratePlanRequest(RequestModel):
    replace_existing: bool = False
    provider: Literal["mock", "openai-compatible"] | None = None


class PlanCharacter(BaseModel):
    name: str
    role: str
    description: str
    goals: list[str]
    personality_traits: list[str]
    speech_style: str
    current_state: str


class PlanLocation(BaseModel):
    name: str
    description: str
    rules: list[str]


class PlanChapter(BaseModel):
    chapter_number: int
    title: str
    objective: str
    summary: str
    key_events: list[str]
    participating_characters: list[str]
    locations: list[str]
    required_facts: list[str]
    forbidden_reveals: list[str]


class PlanForeshadowing(BaseModel):
    id: int
    description: str
    setup_chapter: int
    expected_payoff_chapter: int
    status: str
    importance: str


class PlanResponse(BaseModel):
    project_id: int
    status: ProjectStatus
    themes: list[str]
    world_summary: str
    central_conflict: str
    style_guide: str
    characters: list[PlanCharacter]
    locations: list[PlanLocation]
    chapter_plans: list[PlanChapter]
    foreshadowing: list[PlanForeshadowing]


class VersionPointer(BaseModel):
    id: int
    version: int
    status: ChapterVersionStatus


class ChapterSummary(BaseModel):
    id: int
    project_id: int
    chapter_number: int
    title: str
    objective: str
    status: ChapterStatus
    score: float | None
    has_content: bool
    current_version_id: int | None
    accepted_version_id: int | None
    updated_at: datetime


class ChapterDetail(ChapterSummary):
    outline: str
    outline_metadata: dict[str, object]
    summary: str | None
    current_version: VersionPointer | None
    accepted_version: VersionPointer | None
    best_version: VersionPointer | None
    version_count: int
    conflict_count: int
    workflow_status: WorkflowRunStatus | None
    content: str | None = None


class ContextSummary(BaseModel):
    project_id: int
    chapter_number: int
    characters: list[str]
    locations: list[str]
    known_fact_count: int
    active_foreshadowing: list[str]
    previous_summary_count: int
    metadata: dict[str, object]
    truncated_categories: list[str]


class GenerateChapterRequest(RequestModel):
    regenerate: bool = False
    max_context_chars: int = Field(default=24_000, ge=1_000, le=200_000)
    provider: Literal["mock", "openai-compatible"] | None = None


class ChapterGenerationResponse(BaseModel):
    project_id: int
    chapter_id: int
    chapter_number: int
    version: int
    status: ChapterStatus
    title: str
    summary: str
    fact_count: int
    character_update_count: int
    foreshadowing_update_count: int


class EvaluateChapterRequest(RequestModel):
    force_new_version: bool = True
    provider: Literal["mock", "openai-compatible"] | None = None


class VersionSummary(BaseModel):
    id: int
    chapter_id: int
    version: int
    status: ChapterVersionStatus
    source: str
    parent_version_id: int | None
    score: float | None
    word_count: int
    provider: str
    model: str
    created_at: datetime
    accepted_at: datetime | None


class VersionDetail(VersionSummary):
    title: str
    summary: str
    prompt_versions: dict[str, str]
    changes_made: list[str]
    content: str | None = None


class VersionDiffResponse(BaseModel):
    old_version_id: int
    new_version_id: int
    additions: int
    deletions: int
    changed_line_count: int
    word_count_delta: int
    changes_made: list[str]
    unified_diff: str | None = None
    truncated: bool = False


class EvaluationSummary(BaseModel):
    id: int
    evaluation_version: int
    chapter_version_id: int
    status: EvaluationStatus
    mechanical_score: float
    critic_score: float
    consistency_score: float
    final_score: float
    passed: bool
    recommended_action: str
    created_at: datetime


class EvaluationIssueResponse(BaseModel):
    id: int
    source: str
    code: str
    category: str
    severity: ConflictSeverity
    description: str
    evidence: str | None
    suggestion: str | None
    score_penalty: float
    details: dict[str, object]


class EvaluationDetail(EvaluationSummary):
    raw_scores: dict[str, float]
    weighted_scores: dict[str, float]
    mechanical_metrics: dict[str, object]
    critic_dimensions: dict[str, object]
    blocking_reasons: list[str]
    issues: list[EvaluationIssueResponse]
    evaluator_versions: dict[str, str]
    prompt_versions: dict[str, str]
    provider: str
    model: str


class ConflictResponse(BaseModel):
    id: int
    evaluation_id: int
    project_id: int
    chapter_id: int
    chapter_version_id: int
    conflict_type: ConflictType
    severity: ConflictSeverity
    subject: str
    description: str
    new_evidence: str
    existing_evidence: str | None
    existing_fact_id: int | None
    suggested_resolution: str
    confidence: float
    rule_code: str
    status: ConflictStatus
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ConflictPatchRequest(RequestModel):
    status: ConflictStatus
    resolution_note: str | None = Field(default=None, max_length=2_000)


class FactResponse(BaseModel):
    id: int
    project_id: int
    chapter_id: int
    chapter_number: int
    chapter_version_id: int
    subject: str
    predicate: str
    object: str
    fact_type: str
    valid_from_chapter: int
    valid_to_chapter: int | None
    confidence: float
    source_quote: str
    status: FactStatus


class WorkflowOperation(StrEnum):
    GENERATE_EVALUATE_REVISE = "generate_evaluate_revise"
    EVALUATE_REVISE_EXISTING = "evaluate_revise_existing"


class StartWorkflowRequest(RequestModel):
    operation: WorkflowOperation = WorkflowOperation.GENERATE_EVALUATE_REVISE
    max_revision_attempts: int = Field(default=3, ge=0, le=10)
    provider: Literal["mock", "openai-compatible"] | None = None
    pause_after_node: str | None = Field(default=None, max_length=100)


class WorkflowStatusResponse(BaseModel):
    workflow_run_id: int
    thread_id: str
    project_id: int
    chapter_id: int
    chapter_number: int
    current_node: str
    status: WorkflowRunStatus
    original_version_id: int | None
    current_version_id: int | None
    best_version_id: int | None
    accepted_version_id: int | None
    original_version: int | None
    current_version: int | None
    best_version: int | None
    accepted_version: int | None
    revision_attempt: int
    max_revision_attempts: int
    latest_score: float | None
    blocking_reasons: list[str]
    error_code: str | None
    error_message: str | None
    started_at: datetime
    updated_at: datetime
    finished_at: datetime | None


class WorkflowEventResponse(BaseModel):
    id: int
    node: str
    event_type: WorkflowEventType
    attempt: int
    status: str
    duration_ms: int
    version_id: int | None
    evaluation_id: int | None
    error_code: str | None
    created_at: datetime


class DeleteResponse(BaseModel):
    deleted: bool
    resource_id: int


class HealthResponse(BaseModel):
    status: Literal["ok"]
    service: Literal["storyforge"] = "storyforge"
    version: str
    environment: str


class ReadinessResponse(BaseModel):
    status: Literal["ready"]
    database: Literal["ok"]
    migration_revision: str
    provider: str


class DemoEvaluationSummary(EvaluationSummary):
    issue_count: int
    conflict_count: int


class DemoM6Response(BaseModel):
    model_config = ConfigDict(extra="forbid")

    project: ProjectSummary
    plan_characters: int
    plan_locations: int
    plan_chapters: int
    plan_foreshadowing: int
    chapter: ChapterDetail
    versions: int
    accepted_version: int
    final_score: float
    evaluation: DemoEvaluationSummary
    workflow: WorkflowStatusResponse
    workflow_events: int
    accepted_facts: int
    candidate_facts_visible: int
    future_facts_visible: int
    duplicate_versions: int
    duplicate_evaluations: int
    duplicate_conflicts: int
    duplicate_facts: int


class ScoreRange(RequestModel):
    min_score: TenScore | None = None
    max_score: TenScore | None = None

    @model_validator(mode="after")
    def validate_range(self) -> ScoreRange:
        if (
            self.min_score is not None
            and self.max_score is not None
            and self.min_score > self.max_score
        ):
            raise ValueError("min_score must not exceed max_score")
        return self
