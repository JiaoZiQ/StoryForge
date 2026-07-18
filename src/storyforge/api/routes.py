"""Thin HTTP routes for StoryForge application services through Milestone 8."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response, status

from storyforge.enums import (
    ChapterStatus,
    ConflictSeverity,
    ConflictStatus,
    ConflictType,
    FactStatus,
    GraphEntityType,
    GraphPredicate,
    ProjectStatus,
    ProviderCallStatus,
    TaskType,
)
from storyforge.schemas.api import (
    ChapterDetail,
    ChapterGenerationResponse,
    ChapterSummary,
    ConflictPatchRequest,
    ConflictResponse,
    ContextSummary,
    DeleteResponse,
    EvaluateChapterRequest,
    EvaluationDetail,
    EvaluationSummary,
    FactResponse,
    GenerateChapterRequest,
    GeneratePlanRequest,
    GraphEntityResponse,
    GraphNeighborsResponse,
    GraphRelationResponse,
    HealthResponse,
    MemoryDetail,
    MemoryIndexStatusResponse,
    MemoryReindexRequest,
    MemoryReindexResponse,
    MemorySummary,
    ModelProfileOption,
    ModelProfileUpdateRequest,
    PageResponse,
    PlanResponse,
    PrivacyPolicyUpdateRequest,
    ProjectBudgetResponse,
    ProjectBudgetUpdateRequest,
    ProjectCreateRequest,
    ProjectDetail,
    ProjectModelSettingsResponse,
    ProjectSummary,
    ProjectUpdateRequest,
    ProviderCallResponse,
    ProviderCapabilityResponse,
    ProviderHealthResponse,
    ReadinessResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
    StartWorkflowRequest,
    UsageSummaryResponse,
    VersionDetail,
    VersionDiffResponse,
    VersionSummary,
    WorkflowEventResponse,
    WorkflowStatusResponse,
)

from .dependencies import (
    ChapterServiceDep,
    EvaluationServiceDep,
    GovernanceServiceDep,
    MemoryServiceDep,
    PlanningServiceDep,
    ProjectServiceDep,
    SystemServiceDep,
    WorkflowServiceDep,
)
from .errors import ERROR_RESPONSES

Page = Annotated[int, Query(ge=1)]
PageSize = Annotated[int, Query(ge=1, le=100)]
Score = Annotated[float, Query(ge=0, le=10)]
Confidence = Annotated[float, Query(ge=0, le=1)]
ProjectStatusFilter = Annotated[ProjectStatus | None, Query(alias="status")]
ChapterStatusFilter = Annotated[ChapterStatus | None, Query(alias="status")]
ConflictStatusFilter = Annotated[ConflictStatus | None, Query(alias="status")]
FactStatusFilter = Annotated[FactStatus, Query(alias="status")]
ProviderStatusFilter = Annotated[ProviderCallStatus | None, Query(alias="status")]

api_router = APIRouter(responses=ERROR_RESPONSES)
root_router = APIRouter(responses=ERROR_RESPONSES)


@api_router.get(
    "/providers",
    response_model=list[ProviderCapabilityResponse],
    tags=["providers"],
    summary="List registered provider capabilities",
    operation_id="list_provider_capabilities",
)
def list_provider_capabilities(
    service: GovernanceServiceDep,
) -> list[ProviderCapabilityResponse]:
    return service.providers()


@api_router.get(
    "/providers/health",
    response_model=list[ProviderHealthResponse],
    tags=["providers"],
    summary="Show provider and circuit health without network probes",
    operation_id="list_provider_health",
)
def list_provider_health(service: GovernanceServiceDep) -> list[ProviderHealthResponse]:
    return service.health()


@api_router.get(
    "/system/model-profiles",
    response_model=list[ModelProfileOption],
    tags=["providers"],
    summary="List controlled model profiles",
    operation_id="list_model_profiles",
)
def list_model_profiles(service: GovernanceServiceDep) -> list[ModelProfileOption]:
    return service.model_profiles()


@api_router.get(
    "/projects/{project_id}/usage",
    response_model=UsageSummaryResponse,
    tags=["usage"],
    summary="Summarize project provider usage",
    operation_id="get_project_usage",
)
def get_project_usage(
    project_id: int,
    service: GovernanceServiceDep,
    task_type: TaskType | None = None,
    provider: str | None = None,
    model: str | None = None,
    call_status: ProviderStatusFilter = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> UsageSummaryResponse:
    return service.usage_summary(
        project_id=project_id,
        task_type=task_type,
        provider=provider,
        model=model,
        status=call_status,
        created_from=created_from,
        created_to=created_to,
    )


@api_router.get(
    "/projects/{project_id}/usage/calls",
    response_model=PageResponse[ProviderCallResponse],
    tags=["usage"],
    summary="List content-free provider call audit records",
    operation_id="list_project_provider_calls",
)
def list_project_provider_calls(
    project_id: int,
    service: GovernanceServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    workflow_run_id: int | None = None,
    task_type: TaskType | None = None,
    provider: str | None = None,
    model: str | None = None,
    call_status: ProviderStatusFilter = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
) -> PageResponse[ProviderCallResponse]:
    return service.usage_calls(
        page=page,
        page_size=page_size,
        project_id=project_id,
        workflow_run_id=workflow_run_id,
        task_type=task_type,
        provider=provider,
        model=model,
        status=call_status,
        created_from=created_from,
        created_to=created_to,
    )


@api_router.get(
    "/projects/{project_id}/budget",
    response_model=ProjectBudgetResponse,
    tags=["usage"],
    summary="Show a project budget",
    operation_id="get_project_budget",
)
def get_project_budget(project_id: int, service: GovernanceServiceDep) -> ProjectBudgetResponse:
    return service.budget(project_id)


@api_router.put(
    "/projects/{project_id}/budget",
    response_model=ProjectBudgetResponse,
    tags=["usage"],
    summary="Set project budget limits",
    operation_id="set_project_budget",
)
def set_project_budget(
    project_id: int,
    request: ProjectBudgetUpdateRequest,
    service: GovernanceServiceDep,
) -> ProjectBudgetResponse:
    return service.set_budget(project_id, request)


@api_router.get(
    "/projects/{project_id}/model-settings",
    response_model=ProjectModelSettingsResponse,
    tags=["providers"],
    summary="Show project model and privacy settings",
    operation_id="get_project_model_settings",
)
def get_project_model_settings(
    project_id: int, service: GovernanceServiceDep
) -> ProjectModelSettingsResponse:
    return service.model_settings(project_id)


@api_router.patch(
    "/projects/{project_id}/model-profile",
    response_model=ProjectModelSettingsResponse,
    tags=["providers"],
    summary="Select a controlled model profile",
    operation_id="set_project_model_profile",
)
def set_project_model_profile(
    project_id: int,
    request: ModelProfileUpdateRequest,
    service: GovernanceServiceDep,
) -> ProjectModelSettingsResponse:
    return service.set_model_profile(project_id, request.model_profile)


@api_router.patch(
    "/projects/{project_id}/privacy-policy",
    response_model=ProjectModelSettingsResponse,
    tags=["providers"],
    summary="Select a project privacy policy",
    operation_id="set_project_privacy_policy",
)
def set_project_privacy_policy(
    project_id: int,
    request: PrivacyPolicyUpdateRequest,
    service: GovernanceServiceDep,
) -> ProjectModelSettingsResponse:
    return service.set_privacy_policy(project_id, request.privacy_policy)


@api_router.get(
    "/workflow-runs/{workflow_run_id}/usage",
    response_model=UsageSummaryResponse,
    tags=["usage"],
    summary="Summarize one workflow's provider usage",
    operation_id="get_workflow_usage",
)
def get_workflow_usage(workflow_run_id: int, service: GovernanceServiceDep) -> UsageSummaryResponse:
    return service.usage_summary(workflow_run_id=workflow_run_id)


@root_router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Check process liveness",
    operation_id="root_health",
    response_model_exclude={"environment"},
)
def root_health(service: SystemServiceDep) -> HealthResponse:
    return service.health()


@api_router.get(
    "/health",
    response_model=HealthResponse,
    tags=["system"],
    summary="Check API liveness",
    operation_id="api_health",
)
def api_health(service: SystemServiceDep) -> HealthResponse:
    return service.health()


@api_router.get(
    "/ready",
    response_model=ReadinessResponse,
    tags=["system"],
    summary="Check database and configuration readiness",
    operation_id="api_readiness",
)
def readiness(service: SystemServiceDep) -> ReadinessResponse:
    return service.readiness()


@api_router.post(
    "/projects",
    response_model=ProjectDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["projects"],
    summary="Create a story project",
    operation_id="create_project",
)
def create_project(
    payload: ProjectCreateRequest, response: Response, service: ProjectServiceDep
) -> ProjectDetail:
    project = service.create(payload)
    response.headers["Location"] = f"/api/v1/projects/{project.id}"
    return project


@api_router.get(
    "/projects",
    response_model=PageResponse[ProjectSummary],
    tags=["projects"],
    summary="List story projects",
    operation_id="list_projects",
)
def list_projects(
    service: ProjectServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    project_status: ProjectStatusFilter = None,
    genre: str | None = None,
    language: str | None = None,
    created_from: datetime | None = None,
    created_to: datetime | None = None,
    search: str | None = None,
    sort: Literal["id", "title", "created_at", "updated_at"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> PageResponse[ProjectSummary]:
    return service.list(
        page=page,
        page_size=page_size,
        status=project_status,
        genre=genre,
        language=language,
        created_from=created_from,
        created_to=created_to,
        search=search,
        sort=sort,
        order=order,
    )


@api_router.get(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    tags=["projects"],
    summary="Get a story project",
    operation_id="get_project",
)
def get_project(project_id: int, service: ProjectServiceDep) -> ProjectDetail:
    return service.get(project_id)


@api_router.patch(
    "/projects/{project_id}",
    response_model=ProjectDetail,
    tags=["projects"],
    summary="Update mutable project fields",
    operation_id="update_project",
)
def update_project(
    project_id: int, payload: ProjectUpdateRequest, service: ProjectServiceDep
) -> ProjectDetail:
    return service.update(project_id, payload)


@api_router.delete(
    "/projects/{project_id}",
    response_model=DeleteResponse,
    tags=["projects"],
    summary="Delete an unplanned project",
    operation_id="delete_project",
)
def delete_project(project_id: int, service: ProjectServiceDep) -> DeleteResponse:
    return service.delete(project_id)


@api_router.post(
    "/projects/{project_id}/plan",
    response_model=PlanResponse,
    tags=["planning"],
    summary="Generate or explicitly replace a project plan",
    operation_id="generate_plan",
)
def generate_plan(
    project_id: int, payload: GeneratePlanRequest, service: PlanningServiceDep
) -> PlanResponse:
    return service.generate(project_id, payload)


@api_router.get(
    "/projects/{project_id}/plan",
    response_model=PlanResponse,
    tags=["planning"],
    summary="Get a project plan",
    operation_id="get_plan",
)
def get_plan(project_id: int, service: PlanningServiceDep) -> PlanResponse:
    return service.get(project_id)


@api_router.get(
    "/projects/{project_id}/chapters",
    response_model=PageResponse[ChapterSummary],
    tags=["chapters"],
    summary="List planned chapters without full text",
    operation_id="list_chapters",
)
def list_chapters(
    project_id: int,
    service: ChapterServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    chapter_status: ChapterStatusFilter = None,
    has_content: bool | None = None,
    passed: bool | None = None,
    min_score: Score | None = None,
    max_score: Score | None = None,
    sort: Literal["chapter_number", "status", "score", "updated_at"] = "chapter_number",
    order: Literal["asc", "desc"] = "asc",
) -> PageResponse[ChapterSummary]:
    return service.list_chapters(
        project_id,
        page=page,
        page_size=page_size,
        status=chapter_status.value if chapter_status is not None else None,
        has_content=has_content,
        passed=passed,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
        order=order,
    )


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}",
    response_model=ChapterDetail,
    tags=["chapters"],
    summary="Get logical chapter and version pointers",
    operation_id="get_chapter",
)
def get_chapter(
    project_id: int,
    chapter_number: int,
    service: ChapterServiceDep,
    include_content: bool = False,
) -> ChapterDetail:
    return service.get(project_id, chapter_number, include_content=include_content)


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/context",
    response_model=ContextSummary,
    tags=["chapters"],
    summary="Explain the future-safe writing context",
    operation_id="get_chapter_context",
)
def get_chapter_context(
    project_id: int,
    chapter_number: int,
    service: ChapterServiceDep,
    max_context_chars: Annotated[int, Query(ge=1_000, le=200_000)] = 24_000,
) -> ContextSummary:
    return service.context(project_id, chapter_number, max_context_chars=max_context_chars)


@api_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/generate",
    response_model=ChapterGenerationResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["chapters"],
    summary="Generate and extract one chapter without revision workflow",
    operation_id="generate_chapter",
)
def generate_chapter(
    project_id: int,
    chapter_number: int,
    payload: GenerateChapterRequest,
    service: ChapterServiceDep,
) -> ChapterGenerationResponse:
    return service.generate(project_id, chapter_number, payload)


@api_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/evaluate",
    response_model=EvaluationDetail,
    status_code=status.HTTP_201_CREATED,
    tags=["evaluations"],
    summary="Evaluate a generated chapter without revision",
    operation_id="evaluate_chapter",
)
def evaluate_chapter(
    project_id: int,
    chapter_number: int,
    payload: EvaluateChapterRequest,
    service: EvaluationServiceDep,
) -> EvaluationDetail:
    return service.evaluate(project_id, chapter_number, payload)


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/versions",
    response_model=PageResponse[VersionSummary],
    tags=["versions"],
    summary="List immutable chapter versions",
    operation_id="list_chapter_versions",
)
def list_versions(
    project_id: int,
    chapter_number: int,
    service: ChapterServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
) -> PageResponse[VersionSummary]:
    return service.list_versions(project_id, chapter_number, page=page, page_size=page_size)


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}",
    response_model=VersionDetail,
    tags=["versions"],
    summary="Get one immutable chapter version",
    operation_id="get_chapter_version",
)
def get_version(
    project_id: int,
    chapter_number: int,
    version_id: int,
    service: ChapterServiceDep,
    include_content: bool = False,
) -> VersionDetail:
    return service.get_version(
        project_id, chapter_number, version_id, include_content=include_content
    )


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/diff",
    response_model=VersionDiffResponse,
    tags=["versions"],
    summary="Compare two versions with a bounded deterministic diff",
    operation_id="diff_chapter_version",
)
def diff_version(
    project_id: int,
    chapter_number: int,
    version_id: int,
    service: ChapterServiceDep,
    old_version_id: int | None = None,
    include_unified_diff: bool = False,
) -> VersionDiffResponse:
    return service.diff(
        project_id,
        chapter_number,
        version_id,
        old_version_id=old_version_id,
        include_unified_diff=include_unified_diff,
    )


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/evaluations",
    response_model=PageResponse[EvaluationSummary],
    tags=["evaluations"],
    summary="List immutable chapter evaluations",
    operation_id="list_chapter_evaluations",
)
def list_evaluations(
    project_id: int,
    chapter_number: int,
    service: EvaluationServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    version_id: int | None = None,
    passed: bool | None = None,
    recommended_action: str | None = None,
    min_score: Score | None = None,
    max_score: Score | None = None,
    sort: Literal["created_at", "final_score", "evaluation_version"] = "created_at",
    order: Literal["asc", "desc"] = "desc",
) -> PageResponse[EvaluationSummary]:
    return service.list_evaluations(
        project_id,
        chapter_number,
        page=page,
        page_size=page_size,
        version_id=version_id,
        passed=passed,
        recommended_action=recommended_action,
        min_score=min_score,
        max_score=max_score,
        sort=sort,
        order=order,
    )


@api_router.get(
    "/projects/{project_id}/chapters/{chapter_number}/evaluations/{evaluation_id}",
    response_model=EvaluationDetail,
    tags=["evaluations"],
    summary="Get evaluation scores, issues, and provenance",
    operation_id="get_chapter_evaluation",
)
def get_evaluation(
    project_id: int,
    chapter_number: int,
    evaluation_id: int,
    service: EvaluationServiceDep,
) -> EvaluationDetail:
    return service.get_evaluation(project_id, chapter_number, evaluation_id)


@api_router.get(
    "/projects/{project_id}/conflicts",
    response_model=PageResponse[ConflictResponse],
    tags=["conflicts"],
    summary="List consistency conflicts",
    operation_id="list_project_conflicts",
)
def list_conflicts(
    project_id: int,
    service: EvaluationServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    chapter_number: int | None = None,
    version_id: int | None = None,
    severity: ConflictSeverity | None = None,
    conflict_type: ConflictType | None = None,
    conflict_status: ConflictStatusFilter = None,
    rule_code: str | None = None,
) -> PageResponse[ConflictResponse]:
    return service.list_conflicts(
        project_id,
        page=page,
        page_size=page_size,
        chapter_number=chapter_number,
        version_id=version_id,
        severity=severity,
        conflict_type=conflict_type,
        status=conflict_status,
        rule_code=rule_code,
    )


@api_router.get(
    "/projects/{project_id}/conflicts/{conflict_id}",
    response_model=ConflictResponse,
    tags=["conflicts"],
    summary="Get one consistency conflict",
    operation_id="get_project_conflict",
)
def get_conflict(
    project_id: int, conflict_id: int, service: EvaluationServiceDep
) -> ConflictResponse:
    return service.get_conflict(project_id, conflict_id)


@api_router.patch(
    "/projects/{project_id}/conflicts/{conflict_id}",
    response_model=ConflictResponse,
    tags=["conflicts"],
    summary="Update conflict status and audit note",
    operation_id="update_project_conflict",
)
def update_conflict(
    project_id: int,
    conflict_id: int,
    payload: ConflictPatchRequest,
    service: EvaluationServiceDep,
) -> ConflictResponse:
    return service.update_conflict(project_id, conflict_id, payload)


@api_router.get(
    "/projects/{project_id}/facts",
    response_model=PageResponse[FactResponse],
    tags=["facts"],
    summary="List accepted facts with temporal filtering",
    operation_id="list_project_facts",
)
def list_facts(
    project_id: int,
    service: EvaluationServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    chapter_number: int | None = None,
    subject: str | None = None,
    predicate: str | None = None,
    fact_status: FactStatusFilter = FactStatus.ACCEPTED,
    version_id: int | None = None,
    valid_at_chapter: int | None = None,
    confidence_min: Confidence | None = None,
) -> PageResponse[FactResponse]:
    return service.list_facts(
        project_id,
        page=page,
        page_size=page_size,
        chapter_number=chapter_number,
        subject=subject,
        predicate=predicate,
        status=fact_status,
        version_id=version_id,
        valid_at_chapter=valid_at_chapter,
        confidence_min=confidence_min,
    )


@api_router.get(
    "/projects/{project_id}/facts/{fact_id}",
    response_model=FactResponse,
    tags=["facts"],
    summary="Get one accepted fact",
    operation_id="get_project_fact",
)
def get_fact(project_id: int, fact_id: int, service: EvaluationServiceDep) -> FactResponse:
    return service.get_fact(project_id, fact_id)


@api_router.post(
    "/projects/{project_id}/chapters/{chapter_number}/workflow",
    response_model=WorkflowStatusResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["workflows"],
    summary="Run the synchronous durable chapter workflow",
    operation_id="start_chapter_workflow",
)
def start_workflow(
    project_id: int,
    chapter_number: int,
    payload: StartWorkflowRequest,
    service: WorkflowServiceDep,
) -> WorkflowStatusResponse:
    return service.start(project_id, chapter_number, payload)


@api_router.get(
    "/workflow-runs/{workflow_run_id}",
    response_model=WorkflowStatusResponse,
    tags=["workflows"],
    summary="Get durable workflow status",
    operation_id="get_workflow_run",
)
def get_workflow(workflow_run_id: int, service: WorkflowServiceDep) -> WorkflowStatusResponse:
    return service.get(workflow_run_id)


@api_router.post(
    "/workflow-runs/{workflow_run_id}/resume",
    response_model=WorkflowStatusResponse,
    tags=["workflows"],
    summary="Resume a paused durable workflow",
    operation_id="resume_workflow_run",
)
def resume_workflow(workflow_run_id: int, service: WorkflowServiceDep) -> WorkflowStatusResponse:
    return service.resume(workflow_run_id)


@api_router.post(
    "/workflow-runs/{workflow_run_id}/cancel",
    response_model=WorkflowStatusResponse,
    tags=["workflows"],
    summary="Cooperatively cancel an active workflow",
    operation_id="cancel_workflow_run",
)
def cancel_workflow(workflow_run_id: int, service: WorkflowServiceDep) -> WorkflowStatusResponse:
    return service.cancel(workflow_run_id)


@api_router.get(
    "/workflow-runs/{workflow_run_id}/events",
    response_model=PageResponse[WorkflowEventResponse],
    tags=["workflows"],
    summary="List content-free workflow audit events",
    operation_id="list_workflow_events",
)
def list_workflow_events(
    workflow_run_id: int,
    service: WorkflowServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
) -> PageResponse[WorkflowEventResponse]:
    return service.list_events(workflow_run_id, page=page, page_size=page_size)


@api_router.get(
    "/projects/{project_id}/workflow-runs",
    response_model=PageResponse[WorkflowStatusResponse],
    tags=["workflows"],
    summary="List project workflow runs",
    operation_id="list_project_workflow_runs",
)
def list_project_workflows(
    project_id: int,
    service: WorkflowServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
) -> PageResponse[WorkflowStatusResponse]:
    return service.list_project_runs(project_id, page=page, page_size=page_size)


@api_router.post(
    "/projects/{project_id}/retrieval/search",
    response_model=RetrievalSearchResponse,
    tags=["retrieval"],
    summary="Search accepted past-only story memory",
    operation_id="search_project_memory",
)
def search_memory(
    project_id: int,
    payload: RetrievalSearchRequest,
    service: MemoryServiceDep,
) -> RetrievalSearchResponse:
    return service.search(project_id, payload)


@api_router.get(
    "/projects/{project_id}/memory",
    response_model=PageResponse[MemorySummary],
    tags=["memory"],
    summary="List accepted memory chunks",
    operation_id="list_project_memory",
)
def list_memory(
    project_id: int,
    service: MemoryServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    source_type: str | None = None,
    chapter_number: int | None = None,
) -> PageResponse[MemorySummary]:
    return service.list_memory(
        project_id,
        page=page,
        page_size=page_size,
        source_type=source_type,
        chapter_number=chapter_number,
    )


@api_router.get(
    "/projects/{project_id}/memory/status",
    response_model=PageResponse[MemoryIndexStatusResponse],
    tags=["memory"],
    summary="List memory indexing attempts",
    operation_id="list_project_memory_status",
)
def list_memory_status(
    project_id: int,
    service: MemoryServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
) -> PageResponse[MemoryIndexStatusResponse]:
    return service.list_status(project_id, page=page, page_size=page_size)


@api_router.get(
    "/projects/{project_id}/memory/{memory_id}",
    response_model=MemoryDetail,
    tags=["memory"],
    summary="Get one accepted memory chunk",
    operation_id="get_project_memory",
)
def get_memory(
    project_id: int,
    memory_id: int,
    service: MemoryServiceDep,
    include_content: bool = False,
) -> MemoryDetail:
    return service.get_memory(project_id, memory_id, include_content=include_content)


@api_router.post(
    "/projects/{project_id}/memory/reindex",
    response_model=MemoryReindexResponse,
    tags=["memory"],
    summary="Synchronously reindex accepted memory",
    operation_id="reindex_project_memory",
)
def reindex_memory(
    project_id: int,
    payload: MemoryReindexRequest,
    service: MemoryServiceDep,
) -> MemoryReindexResponse:
    return service.reindex(project_id, payload)


@api_router.get(
    "/projects/{project_id}/graph/entities",
    response_model=PageResponse[GraphEntityResponse],
    tags=["graph"],
    summary="List accepted graph entities",
    operation_id="list_project_graph_entities",
)
def list_graph_entities(
    project_id: int,
    service: MemoryServiceDep,
    page: Page = 1,
    page_size: PageSize = 20,
    entity_type: GraphEntityType | None = None,
    search: str | None = None,
) -> PageResponse[GraphEntityResponse]:
    return service.list_entities(
        project_id,
        page=page,
        page_size=page_size,
        entity_type=entity_type,
        search=search,
    )


@api_router.get(
    "/projects/{project_id}/graph/entities/{entity_id}",
    response_model=GraphEntityResponse,
    tags=["graph"],
    summary="Get one accepted graph entity",
    operation_id="get_project_graph_entity",
)
def get_graph_entity(
    project_id: int, entity_id: int, service: MemoryServiceDep
) -> GraphEntityResponse:
    return service.get_entity(project_id, entity_id)


@api_router.get(
    "/projects/{project_id}/graph/relations",
    response_model=PageResponse[GraphRelationResponse],
    tags=["graph"],
    summary="List past-only accepted graph relations",
    operation_id="list_project_graph_relations",
)
def list_graph_relations(
    project_id: int,
    service: MemoryServiceDep,
    current_chapter: Annotated[int, Query(gt=0)],
    page: Page = 1,
    page_size: PageSize = 20,
    predicate: GraphPredicate | None = None,
) -> PageResponse[GraphRelationResponse]:
    return service.list_relations(
        project_id,
        current_chapter=current_chapter,
        page=page,
        page_size=page_size,
        predicate=predicate,
    )


@api_router.get(
    "/projects/{project_id}/graph/neighbors",
    response_model=GraphNeighborsResponse,
    tags=["graph"],
    summary="Expand one graph entity by one or two hops",
    operation_id="get_project_graph_neighbors",
)
def graph_neighbors(
    project_id: int,
    service: MemoryServiceDep,
    entity_id: Annotated[int, Query(gt=0)],
    current_chapter: Annotated[int, Query(gt=0)],
    max_hops: Annotated[int, Query(ge=1, le=2)] = 1,
) -> GraphNeighborsResponse:
    return service.neighbors(
        project_id,
        entity_id,
        current_chapter=current_chapter,
        max_hops=max_hops,
    )
