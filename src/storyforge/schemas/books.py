"""Safe API and CLI schemas for full-book workflows and analyses."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from storyforge.enums import (
    BookRunMode,
    BookRunStatus,
    BookSnapshotStatus,
    ModelProfile,
    PrivacyPolicy,
)


class BookRunCreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: BookRunMode = BookRunMode.SEQUENTIAL
    max_chapter_retries: int | None = Field(default=None, ge=0, le=10)
    max_global_revision_rounds: int | None = Field(default=None, ge=0, le=5)
    model_profile: ModelProfile | None = None
    privacy_policy: PrivacyPolicy | None = None
    max_estimated_cost: Decimal | None = Field(default=None, gt=0)
    max_total_tokens: int | None = Field(default=None, gt=0)
    max_provider_calls: int | None = Field(default=None, gt=0)


class BookRunAcceptedResponse(BaseModel):
    book_run_id: int
    job_id: int
    reused: bool
    status: BookRunStatus
    status_url: str
    events_url: str


class BookRunResumeRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_estimated_cost: Decimal | None = Field(default=None, gt=0)
    max_total_tokens: int | None = Field(default=None, gt=0)
    max_provider_calls: int | None = Field(default=None, gt=0)


class BookRunResponse(BaseModel):
    id: int
    project_id: int
    job_id: int | None
    status: BookRunStatus
    mode: BookRunMode
    total_chapters: int
    completed_chapters: int
    accepted_chapters: int
    failed_chapters: int
    needs_review_chapters: int
    current_chapter_number: int | None
    current_global_revision_round: int
    max_global_revision_rounds: int
    current_node: str
    progress: int
    book_snapshot_id: int | None
    best_snapshot_id: int | None
    blocking_reasons: list[str]
    chapter_status: dict[str, str]
    periodic_checks: list[dict[str, object]]
    spent_cost: Decimal
    remaining_cost: Decimal
    used_tokens: int
    remaining_tokens: int
    provider_calls: int
    remaining_provider_calls: int
    started_at: datetime | None
    updated_at: datetime
    finished_at: datetime | None
    error_code: str | None
    error_message: str | None


class BookRunPageResponse(BaseModel):
    items: list[BookRunResponse]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class BookSnapshotResponse(BaseModel):
    id: int
    project_id: int
    book_run_id: int
    snapshot_number: int
    status: BookSnapshotStatus
    chapter_version_map: dict[str, int]
    total_words: int
    chapter_count: int
    accepted_chapter_count: int
    content_hash: str
    evaluation_summary: dict[str, object]
    created_at: datetime
    accepted_at: datetime | None


class BookSnapshotPageResponse(BaseModel):
    items: list[BookSnapshotResponse]
    total_items: int


class BookEvaluationResponse(BaseModel):
    id: int
    book_snapshot_id: int
    evaluation_version: int
    final_score: float
    passed: bool
    dimension_scores: dict[str, float]
    blocking_reasons: list[str]
    recommended_action: str
    priority_chapters: list[int]
    global_issues: list[dict[str, object]]
    evaluator_versions: dict[str, str]
    prompt_versions: dict[str, str]
    created_at: datetime


class TimelinePageResponse(BaseModel):
    items: list[dict[str, object]]
    page: int
    page_size: int
    total_items: int
    total_pages: int


class BookAnalysisResponse(BaseModel):
    snapshot_id: int
    kind: str
    score: float | None = None
    summary: dict[str, object]
    items: list[dict[str, object]]


class BookRevisionPlanResponse(BaseModel):
    id: int
    book_snapshot_id: int
    revision_round: int
    global_objectives: list[str]
    dependency_order: list[int]
    must_preserve: list[str]
    global_constraints: list[str]
    estimated_calls: int
    estimated_tokens: int
    estimated_cost: Decimal
    status: str
    tasks: list[dict[str, object]]
