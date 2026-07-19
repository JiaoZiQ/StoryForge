"""Stable API and CLI boundary models for Milestone 6."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from storyforge.enums import (
    BudgetPeriod,
    ChapterStatus,
    ChapterVersionStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    EvaluationStatus,
    FactStatus,
    GraphEntityType,
    GraphPredicate,
    MemoryIndexStatus,
    MemoryStatus,
    ModelProfile,
    PrivacyPolicy,
    ProjectStatus,
    ProviderCallStatus,
    TaskType,
    TokenUsageSource,
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
    memory_hit_count: int = 0
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
    queue: Literal["ok", "inline"] = "inline"


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
    evaluations: int
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


class RetrievalSearchRequest(RequestModel):
    query: str = Field(min_length=1, max_length=2_000)
    current_chapter: int = Field(gt=0)
    character_names: list[str] = Field(default_factory=list, max_length=50)
    location_names: list[str] = Field(default_factory=list, max_length=50)
    source_types: list[str] = Field(default_factory=list, max_length=20)
    top_k: int = Field(default=20, ge=1, le=100)
    max_context_chars: int = Field(default=16_000, ge=100, le=100_000)
    include_sources: list[Literal["keyword", "vector", "fact", "graph"]] | None = None
    debug: bool = False


class RetrievalHitResponse(BaseModel):
    id: int
    source_type: str
    content: str
    score: float
    sources: list[str]
    chapter_number: int | None
    version_id: int | None
    entity_names: list[str]
    relation_path: list[str]
    explanation: str


class RetrievalSearchResponse(BaseModel):
    query: str
    hits: list[RetrievalHitResponse]
    total_candidates: int
    keyword_candidates: int
    vector_candidates: int
    fact_candidates: int
    graph_candidates: int
    deduplicated_count: int
    omitted_count: int
    estimated_chars: int
    retrieval_version: str
    filters_applied: list[str]
    degraded: bool
    degraded_reasons: list[str]


class MemorySummary(BaseModel):
    id: int
    project_id: int
    chapter_id: int | None
    chapter_version_id: int | None
    source_type: str
    source_id: str
    chunk_index: int
    content_preview: str
    content_hash: str
    token_estimate: int
    character_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    status: MemoryStatus
    valid_from_chapter: int
    valid_to_chapter: int | None
    created_at: datetime


class MemoryDetail(MemorySummary):
    content: str | None = None
    metadata: dict[str, object]


class MemoryReindexRequest(RequestModel):
    chapter_version_id: int | None = Field(default=None, gt=0)
    all_accepted_chapters: bool = False
    force: bool = False

    @model_validator(mode="after")
    def validate_scope(self) -> MemoryReindexRequest:
        if (self.chapter_version_id is None) == (not self.all_accepted_chapters):
            raise ValueError("Specify exactly one of chapter_version_id or all_accepted_chapters")
        return self


class MemoryReindexItem(BaseModel):
    chapter_version_id: int
    status: str
    chunk_count: int
    graph_entity_count: int
    graph_relation_count: int
    degraded: bool


class MemoryReindexResponse(BaseModel):
    project_id: int
    results: list[MemoryReindexItem]


class MemoryIndexStatusResponse(BaseModel):
    id: int
    project_id: int
    chapter_version_id: int
    status: MemoryIndexStatus
    attempt_count: int
    chunk_count: int
    graph_entity_count: int
    graph_relation_count: int
    embedding_provider: str
    embedding_model: str
    embedding_dimensions: int
    error_code: str | None


class GraphEntityResponse(BaseModel):
    id: int
    project_id: int
    entity_type: GraphEntityType
    canonical_name: str
    description: str | None
    aliases: list[str]
    confidence: float
    status: MemoryStatus
    source_chapter_id: int | None
    source_version_id: int | None


class GraphRelationResponse(BaseModel):
    id: int
    project_id: int
    subject_entity_id: int
    subject_name: str
    predicate: GraphPredicate
    object_entity_id: int
    object_name: str
    confidence: float
    valid_from_chapter: int
    valid_to_chapter: int | None
    status: MemoryStatus
    evidence: str
    source_version_id: int | None


class GraphNeighborsResponse(BaseModel):
    project_id: int
    entity_id: int
    current_chapter: int
    max_hops: int
    entities: list[GraphEntityResponse]
    relations: list[GraphRelationResponse]


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


class ProviderCapabilityResponse(BaseModel):
    provider: str
    model: str
    model_type: Literal["chat", "embedding"]
    context_window: int
    max_output_tokens: int
    supports_structured_output: bool
    supports_json_schema: bool
    supports_embeddings: bool
    embedding_dimensions: int | None
    enabled: bool
    pricing_available: bool


class ProviderHealthResponse(BaseModel):
    provider: str
    model: str
    enabled: bool
    health_status: Literal["healthy", "configured", "disabled", "unavailable"]
    circuit_status: Literal["closed", "open", "half_open"]
    pricing_available: bool
    capabilities: list[str]


class ProviderCallResponse(BaseModel):
    id: int
    project_id: int | None
    workflow_run_id: int | None
    chapter_id: int | None
    chapter_version_id: int | None
    task_type: TaskType
    provider: str
    model: str
    profile: ModelProfile
    privacy_policy: PrivacyPolicy
    prompt_name: str
    prompt_version: str
    status: ProviderCallStatus
    attempt: int
    fallback_index: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    total_tokens: int
    usage_source: TokenUsageSource
    estimated_cost: Decimal | None
    billed_cost: Decimal | None
    currency: str
    latency_ms: int
    provider_request_id: str | None
    error_code: str | None
    created_at: datetime
    completed_at: datetime | None


class UsageSummaryResponse(BaseModel):
    calls: int
    succeeded: int
    failures: int
    input_tokens: int
    output_tokens: int
    cached_input_tokens: int
    total_tokens: int
    estimated_cost: Decimal | None
    billed_cost: Decimal | None
    fallback_count: int
    timeout_count: int
    rate_limit_count: int
    average_latency_ms: Decimal
    currency: str


class ProjectBudgetResponse(BaseModel):
    project_id: int
    currency: str
    soft_limit: Decimal
    hard_limit: Decimal
    period: BudgetPeriod
    spent_estimated: Decimal
    spent_billed: Decimal
    reserved_estimated: Decimal
    alert_thresholds: list[str]
    enabled: bool
    remaining_estimated: Decimal


class ProjectBudgetUpdateRequest(RequestModel):
    currency: str = Field(min_length=3, max_length=3, pattern=r"^[A-Z]{3}$")
    soft_limit: Decimal = Field(ge=0, max_digits=18, decimal_places=8)
    hard_limit: Decimal = Field(gt=0, max_digits=18, decimal_places=8)
    period: BudgetPeriod = BudgetPeriod.LIFETIME
    enabled: bool = True

    @model_validator(mode="after")
    def validate_limits(self) -> ProjectBudgetUpdateRequest:
        if self.soft_limit > self.hard_limit:
            raise ValueError("soft_limit must not exceed hard_limit")
        return self


class ProjectModelSettingsResponse(BaseModel):
    project_id: int
    model_profile: ModelProfile
    privacy_policy: PrivacyPolicy


class ModelProfileUpdateRequest(RequestModel):
    model_profile: ModelProfile


class PrivacyPolicyUpdateRequest(RequestModel):
    privacy_policy: PrivacyPolicy


class ModelProfileOption(BaseModel):
    name: ModelProfile
    description: str
    external_allowed: bool
