import { parseApiResponse, rawApi } from "./client";
import {
  chapterDetailSchema,
  chapterPageSchema,
  conflictPageSchema,
  conflictSchema,
  contextSchema,
  evaluationDetailSchema,
  evaluationPageSchema,
  factPageSchema,
  generationSchema,
  graphEntityPageSchema,
  graphNeighborsSchema,
  graphRelationPageSchema,
  healthSchema,
  memoryPageSchema,
  memoryStatusPageSchema,
  modelProfileOptionSchema,
  modelSettingsSchema,
  planSchema,
  projectDetailSchema,
  projectPageSchema,
  projectBudgetSchema,
  providerCallPageSchema,
  providerCapabilitySchema,
  providerHealthSchema,
  readinessSchema,
  reindexSchema,
  retrievalSchema,
  usageSummarySchema,
  versionDetailSchema,
  versionDiffSchema,
  versionPageSchema,
  workflowEventPageSchema,
  workflowPageSchema,
  workflowSchema,
} from "./schemas";
import type {
  ChapterDetail,
  ChapterGenerationResponse,
  ChapterSummary,
  ConflictResponse,
  ContextSummary,
  EvaluationDetail,
  EvaluationSummary,
  FactResponse,
  GraphEntityResponse,
  GraphNeighborsResponse,
  GraphRelationResponse,
  HealthResponse,
  MemoryIndexStatusResponse,
  MemoryReindexResponse,
  MemorySummary,
  ModelProfileOption,
  Page,
  PlanResponse,
  ProjectCreateRequest,
  ProjectDetail,
  ProjectSummary,
  ProjectBudgetResponse,
  ProjectModelSettingsResponse,
  ProviderCallResponse,
  ProviderCapabilityResponse,
  ProviderHealthResponse,
  ReadinessResponse,
  RetrievalSearchRequest,
  RetrievalSearchResponse,
  UsageSummaryResponse,
  VersionDetail,
  VersionDiffResponse,
  VersionSummary,
  WorkflowEventResponse,
  WorkflowStatusResponse,
} from "./types";

export type ProjectListFilters = {
  page?: number;
  pageSize?: number;
  status?: string;
  genre?: string;
  search?: string;
  sortBy?: "created_at" | "updated_at" | "title";
  sortOrder?: "asc" | "desc";
};

export const storyforgeApi = {
  listProviders: (signal?: AbortSignal) =>
    parseApiResponse<ProviderCapabilityResponse[]>(
      rawApi.GET("/api/v1/providers", { signal }),
      providerCapabilitySchema.array(),
    ),
  providerHealth: (signal?: AbortSignal) =>
    parseApiResponse<ProviderHealthResponse[]>(
      rawApi.GET("/api/v1/providers/health", { signal }),
      providerHealthSchema.array(),
    ),
  listModelProfiles: (signal?: AbortSignal) =>
    parseApiResponse<ModelProfileOption[]>(
      rawApi.GET("/api/v1/system/model-profiles", { signal }),
      modelProfileOptionSchema.array(),
    ),
  health: () =>
    parseApiResponse<HealthResponse>(
      rawApi.GET("/api/v1/health"),
      healthSchema,
    ),
  readiness: () =>
    parseApiResponse<ReadinessResponse>(
      rawApi.GET("/api/v1/ready"),
      readinessSchema,
    ),
  listProjects: (filters: ProjectListFilters = {}, signal?: AbortSignal) =>
    parseApiResponse<Page<ProjectSummary>>(
      rawApi.GET("/api/v1/projects", {
        signal,
        params: {
          query: {
            page: filters.page ?? 1,
            page_size: filters.pageSize ?? 20,
            status: filters.status as ProjectSummary["status"] | undefined,
            genre: filters.genre,
            search: filters.search,
            sort_by: filters.sortBy ?? "updated_at",
            sort_order: filters.sortOrder ?? "desc",
          },
        },
      }),
      projectPageSchema,
    ),
  createProject: (body: ProjectCreateRequest, signal?: AbortSignal) =>
    parseApiResponse<ProjectDetail>(
      rawApi.POST("/api/v1/projects", { body, signal }),
      projectDetailSchema,
    ),
  getProject: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<ProjectDetail>(
      rawApi.GET("/api/v1/projects/{project_id}", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      projectDetailSchema,
    ),
  getPlan: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<PlanResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/plan", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      planSchema,
    ),
  generatePlan: (
    projectId: number,
    replaceExisting = false,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<PlanResponse>(
      rawApi.POST("/api/v1/projects/{project_id}/plan", {
        signal,
        params: { path: { project_id: projectId } },
        body: { replace_existing: replaceExisting },
      }),
      planSchema,
    ),
  listChapters: (
    projectId: number,
    filters: { page?: number; status?: string; hasContent?: boolean } = {},
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<ChapterSummary>>(
      rawApi.GET("/api/v1/projects/{project_id}/chapters", {
        signal,
        params: {
          path: { project_id: projectId },
          query: {
            page: filters.page ?? 1,
            page_size: 50,
            status: filters.status as ChapterSummary["status"] | undefined,
            has_content: filters.hasContent,
            sort_by: "chapter_number",
            sort_order: "asc",
          },
        },
      }),
      chapterPageSchema,
    ),
  getChapter: (
    projectId: number,
    chapterNumber: number,
    includeContent = false,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<ChapterDetail>(
      rawApi.GET("/api/v1/projects/{project_id}/chapters/{chapter_number}", {
        signal,
        params: {
          path: { project_id: projectId, chapter_number: chapterNumber },
          query: { include_content: includeContent },
        },
      }),
      chapterDetailSchema,
    ),
  getContext: (
    projectId: number,
    chapterNumber: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<ContextSummary>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/context",
        {
          signal,
          params: {
            path: { project_id: projectId, chapter_number: chapterNumber },
          },
        },
      ),
      contextSchema,
    ),
  generateChapter: (projectId: number, chapterNumber: number) =>
    parseApiResponse<ChapterGenerationResponse>(
      rawApi.POST(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/generate",
        {
          params: {
            path: { project_id: projectId, chapter_number: chapterNumber },
          },
          body: { regenerate: false, max_context_chars: 24000 },
        },
      ),
      generationSchema,
    ),
  startWorkflow: (projectId: number, chapterNumber: number) =>
    parseApiResponse<WorkflowStatusResponse>(
      rawApi.POST(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/workflow",
        {
          params: {
            path: { project_id: projectId, chapter_number: chapterNumber },
          },
          body: {
            operation: "generate_evaluate_revise",
            max_revision_attempts: 3,
          },
        },
      ),
      workflowSchema,
    ),
  listVersions: (
    projectId: number,
    chapterNumber: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<VersionSummary>>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/versions",
        {
          signal,
          params: {
            path: { project_id: projectId, chapter_number: chapterNumber },
            query: { page: 1, page_size: 100 },
          },
        },
      ),
      versionPageSchema,
    ),
  getVersion: (
    projectId: number,
    chapterNumber: number,
    versionId: number,
    includeContent = false,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<VersionDetail>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}",
        {
          signal,
          params: {
            path: {
              project_id: projectId,
              chapter_number: chapterNumber,
              version_id: versionId,
            },
            query: { include_content: includeContent },
          },
        },
      ),
      versionDetailSchema,
    ),
  diffVersions: (
    projectId: number,
    chapterNumber: number,
    newVersionId: number,
    oldVersionId: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<VersionDiffResponse>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/versions/{version_id}/diff",
        {
          signal,
          params: {
            path: {
              project_id: projectId,
              chapter_number: chapterNumber,
              version_id: newVersionId,
            },
            query: { old_version_id: oldVersionId, include_unified_diff: true },
          },
        },
      ),
      versionDiffSchema,
    ),
  listEvaluations: (
    projectId: number,
    chapterNumber: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<EvaluationSummary>>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/evaluations",
        {
          signal,
          params: {
            path: { project_id: projectId, chapter_number: chapterNumber },
            query: { page: 1, page_size: 100 },
          },
        },
      ),
      evaluationPageSchema,
    ),
  getEvaluation: (
    projectId: number,
    chapterNumber: number,
    evaluationId: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<EvaluationDetail>(
      rawApi.GET(
        "/api/v1/projects/{project_id}/chapters/{chapter_number}/evaluations/{evaluation_id}",
        {
          signal,
          params: {
            path: {
              project_id: projectId,
              chapter_number: chapterNumber,
              evaluation_id: evaluationId,
            },
          },
        },
      ),
      evaluationDetailSchema,
    ),
  listConflicts: (
    projectId: number,
    filters: {
      severity?: string;
      status?: string;
      chapterNumber?: number;
    } = {},
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<ConflictResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/conflicts", {
        signal,
        params: {
          path: { project_id: projectId },
          query: {
            page: 1,
            page_size: 100,
            severity: filters.severity as
              ConflictResponse["severity"] | undefined,
            status: filters.status as ConflictResponse["status"] | undefined,
            chapter_number: filters.chapterNumber,
            sort_by: "severity",
            sort_order: "asc",
          },
        },
      }),
      conflictPageSchema,
    ),
  updateConflict: (
    projectId: number,
    conflictId: number,
    status: "open" | "resolved" | "ignored" | "false_positive",
    resolutionNote?: string,
  ) =>
    parseApiResponse<ConflictResponse>(
      rawApi.PATCH("/api/v1/projects/{project_id}/conflicts/{conflict_id}", {
        params: { path: { project_id: projectId, conflict_id: conflictId } },
        body: { status, resolution_note: resolutionNote },
      }),
      conflictSchema,
    ),
  listFacts: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<Page<FactResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/facts", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100, status: "accepted" },
        },
      }),
      factPageSchema,
    ),
  listWorkflows: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<Page<WorkflowStatusResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/workflow-runs", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100 },
        },
      }),
      workflowPageSchema,
    ),
  getWorkflow: (workflowRunId: number, signal?: AbortSignal) =>
    parseApiResponse<WorkflowStatusResponse>(
      rawApi.GET("/api/v1/workflow-runs/{workflow_run_id}", {
        signal,
        params: { path: { workflow_run_id: workflowRunId } },
      }),
      workflowSchema,
    ),
  listWorkflowEvents: (workflowRunId: number, signal?: AbortSignal) =>
    parseApiResponse<Page<WorkflowEventResponse>>(
      rawApi.GET("/api/v1/workflow-runs/{workflow_run_id}/events", {
        signal,
        params: {
          path: { workflow_run_id: workflowRunId },
          query: { page: 1, page_size: 100 },
        },
      }),
      workflowEventPageSchema,
    ),
  resumeWorkflow: (workflowRunId: number) =>
    parseApiResponse<WorkflowStatusResponse>(
      rawApi.POST("/api/v1/workflow-runs/{workflow_run_id}/resume", {
        params: { path: { workflow_run_id: workflowRunId } },
      }),
      workflowSchema,
    ),
  cancelWorkflow: (workflowRunId: number) =>
    parseApiResponse<WorkflowStatusResponse>(
      rawApi.POST("/api/v1/workflow-runs/{workflow_run_id}/cancel", {
        params: { path: { workflow_run_id: workflowRunId } },
      }),
      workflowSchema,
    ),
  searchMemory: (
    projectId: number,
    body: RetrievalSearchRequest,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<RetrievalSearchResponse>(
      rawApi.POST("/api/v1/projects/{project_id}/retrieval/search", {
        signal,
        params: { path: { project_id: projectId } },
        body,
      }),
      retrievalSchema,
    ),
  listMemory: (
    projectId: number,
    filters: { sourceType?: string; chapterNumber?: number } = {},
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<MemorySummary>>(
      rawApi.GET("/api/v1/projects/{project_id}/memory", {
        signal,
        params: {
          path: { project_id: projectId },
          query: {
            page: 1,
            page_size: 100,
            source_type: filters.sourceType,
            chapter_number: filters.chapterNumber,
            include_content: false,
          },
        },
      }),
      memoryPageSchema,
    ),
  listMemoryStatus: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<Page<MemoryIndexStatusResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/memory/status", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100 },
        },
      }),
      memoryStatusPageSchema,
    ),
  reindexMemory: (projectId: number) =>
    parseApiResponse<MemoryReindexResponse>(
      rawApi.POST("/api/v1/projects/{project_id}/memory/reindex", {
        params: { path: { project_id: projectId } },
        body: { all_accepted_chapters: true, force: false },
      }),
      reindexSchema,
    ),
  listGraphEntities: (
    projectId: number,
    search?: string,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<GraphEntityResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/graph/entities", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100, search },
        },
      }),
      graphEntityPageSchema,
    ),
  listGraphRelations: (
    projectId: number,
    currentChapter: number,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<Page<GraphRelationResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/graph/relations", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { current_chapter: currentChapter, page: 1, page_size: 100 },
        },
      }),
      graphRelationPageSchema,
    ),
  graphNeighbors: (
    projectId: number,
    entityId: number,
    currentChapter: number,
    maxHops: 1 | 2,
    signal?: AbortSignal,
  ) =>
    parseApiResponse<GraphNeighborsResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/graph/neighbors", {
        signal,
        params: {
          path: { project_id: projectId },
          query: {
            entity_id: entityId,
            current_chapter: currentChapter,
            max_hops: maxHops,
          },
        },
      }),
      graphNeighborsSchema,
    ),
  getUsage: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<UsageSummaryResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/usage", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      usageSummarySchema,
    ),
  getWorkflowUsage: (workflowRunId: number, signal?: AbortSignal) =>
    parseApiResponse<UsageSummaryResponse>(
      rawApi.GET("/api/v1/workflow-runs/{workflow_run_id}/usage", {
        signal,
        params: { path: { workflow_run_id: workflowRunId } },
      }),
      usageSummarySchema,
    ),
  listUsageCalls: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<Page<ProviderCallResponse>>(
      rawApi.GET("/api/v1/projects/{project_id}/usage/calls", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100 },
        },
      }),
      providerCallPageSchema,
    ),
  getBudget: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<ProjectBudgetResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/budget", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      projectBudgetSchema,
    ),
  setBudget: (
    projectId: number,
    body: {
      currency: string;
      soft_limit: string;
      hard_limit: string;
      period: "lifetime" | "daily" | "monthly";
      enabled: boolean;
    },
  ) =>
    parseApiResponse<ProjectBudgetResponse>(
      rawApi.PUT("/api/v1/projects/{project_id}/budget", {
        params: { path: { project_id: projectId } },
        body,
      }),
      projectBudgetSchema,
    ),
  getModelSettings: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<ProjectModelSettingsResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/model-settings", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      modelSettingsSchema,
    ),
  setModelProfile: (
    projectId: number,
    model_profile: "offline" | "economy" | "balanced" | "quality",
  ) =>
    parseApiResponse<ProjectModelSettingsResponse>(
      rawApi.PATCH("/api/v1/projects/{project_id}/model-profile", {
        params: { path: { project_id: projectId } },
        body: { model_profile },
      }),
      modelSettingsSchema,
    ),
  setPrivacyPolicy: (
    projectId: number,
    privacy_policy: "offline" | "strict" | "standard",
  ) =>
    parseApiResponse<ProjectModelSettingsResponse>(
      rawApi.PATCH("/api/v1/projects/{project_id}/privacy-policy", {
        params: { path: { project_id: projectId } },
        body: { privacy_policy },
      }),
      modelSettingsSchema,
    ),
};
