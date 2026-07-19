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
  retrievalSchema,
  usageSummarySchema,
  versionDetailSchema,
  versionDiffSchema,
  versionPageSchema,
  workflowEventPageSchema,
  workflowPageSchema,
  workflowSchema,
  jobSchema,
  jobAcceptedSchema,
  jobPageSchema,
  jobEventPageSchema,
  queueHealthSchema,
  bookRunAcceptedSchema,
  bookRunPageSchema,
  bookRunSchema,
  bookSnapshotPageSchema,
  bookSnapshotSchema,
  bookEvaluationSchema,
  bookAnalysisSchema,
  timelinePageSchema,
  bookRevisionPlanSchema,
} from "./schemas";
import type {
  ChapterDetail,
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
  JobResponse,
  JobAcceptedResponse,
  JobCreateRequest,
  JobPageResponse,
  JobEventPageResponse,
  QueueHealthResponse,
  BookRunCreateRequest,
  BookRunAcceptedResponse,
  BookRunResponse,
  BookRunPageResponse,
  BookSnapshotResponse,
  BookSnapshotPageResponse,
  BookEvaluationResponse,
  BookAnalysisResponse,
  TimelinePageResponse,
  BookRevisionPlanResponse,
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
  createJob: (body: JobCreateRequest, signal?: AbortSignal) =>
    parseApiResponse<JobAcceptedResponse>(
      rawApi.POST("/api/v1/jobs", { body, signal }),
      jobAcceptedSchema,
    ),
  listJobs: (
    filters: {
      status?: string;
      jobType?: string;
      projectId?: number;
      chapterNumber?: number;
      createdFrom?: string;
      createdTo?: string;
    } = {},
    signal?: AbortSignal,
  ) =>
    parseApiResponse<JobPageResponse>(
      rawApi.GET("/api/v1/jobs", {
        signal,
        params: {
          query: {
            page: 1,
            page_size: 100,
            status: filters.status as JobResponse["status"] | undefined,
            job_type: filters.jobType as JobResponse["job_type"] | undefined,
            project_id: filters.projectId,
            chapter_number: filters.chapterNumber,
            created_from: filters.createdFrom,
            created_to: filters.createdTo,
          },
        },
      }),
      jobPageSchema,
    ),
  getJob: (jobId: number, signal?: AbortSignal) =>
    parseApiResponse<JobResponse>(
      rawApi.GET("/api/v1/jobs/{job_id}", {
        signal,
        params: { path: { job_id: jobId } },
      }),
      jobSchema,
    ),
  queueHealth: (signal?: AbortSignal) =>
    parseApiResponse<QueueHealthResponse>(
      rawApi.GET("/api/v1/queue/health", { signal }),
      queueHealthSchema,
    ),
  listJobEvents: (jobId: number, signal?: AbortSignal) =>
    parseApiResponse<JobEventPageResponse>(
      rawApi.GET("/api/v1/jobs/{job_id}/events", {
        signal,
        params: { path: { job_id: jobId }, query: { page: 1, page_size: 500 } },
      }),
      jobEventPageSchema,
    ),
  controlJob: (
    jobId: number,
    action: "cancel" | "pause" | "resume" | "retry" | "discard",
  ) => {
    const path = `/api/v1/jobs/${jobId}/${action}`;
    return fetch(`/backend${path}`, { method: "POST" }).then(
      async (response) => {
        const payload: unknown = await response.json();
        const parsed = jobSchema.safeParse(payload);
        if (!response.ok || !parsed.success)
          throw new Error("Job control failed");
        return parsed.data as JobResponse;
      },
    );
  },
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
    storyforgeApi.createJob(
      {
        job_type: "generate_plan",
        project_id: projectId,
        operation: "generate",
        payload: { replace_existing: replaceExisting },
        priority: 5,
      },
      signal,
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
    storyforgeApi.createJob({
      job_type: "generate_chapter",
      project_id: projectId,
      chapter_number: chapterNumber,
      operation: "generate",
      payload: { regenerate: false, max_context_chars: 24000 },
      priority: 5,
    }),
  startWorkflow: (projectId: number, chapterNumber: number) =>
    storyforgeApi.createJob({
      job_type: "run_chapter_workflow",
      project_id: projectId,
      chapter_number: chapterNumber,
      operation: "generate_evaluate_revise",
      payload: { max_revision_attempts: 3 },
      priority: 5,
    }),
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
    storyforgeApi.createJob({
      job_type: "reindex_memory",
      project_id: projectId,
      operation: "reindex",
      payload: { all_accepted_chapters: true, force: false },
      priority: 5,
    }),
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
  createBookRun: (
    projectId: number,
    body: BookRunCreateRequest,
    idempotencyKey: string,
  ) =>
    parseApiResponse<BookRunAcceptedResponse>(
      rawApi.POST("/api/v1/projects/{project_id}/book-runs", {
        params: { path: { project_id: projectId } },
        body,
        headers: { "Idempotency-Key": idempotencyKey },
      }),
      bookRunAcceptedSchema,
    ),
  listBookRuns: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<BookRunPageResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/book-runs", {
        signal,
        params: {
          path: { project_id: projectId },
          query: { page: 1, page_size: 100 },
        },
      }),
      bookRunPageSchema,
    ),
  getBookRun: (runId: number, signal?: AbortSignal) =>
    parseApiResponse<BookRunResponse>(
      rawApi.GET("/api/v1/book-runs/{book_run_id}", {
        signal,
        params: { path: { book_run_id: runId } },
      }),
      bookRunSchema,
    ),
  controlBookRun: (runId: number, action: "pause" | "resume" | "cancel") => {
    const params = { path: { book_run_id: runId } };
    if (action === "pause")
      return parseApiResponse<BookRunResponse>(
        rawApi.POST("/api/v1/book-runs/{book_run_id}/pause", { params }),
        bookRunSchema,
      );
    if (action === "cancel")
      return parseApiResponse<BookRunResponse>(
        rawApi.POST("/api/v1/book-runs/{book_run_id}/cancel", { params }),
        bookRunSchema,
      );
    return parseApiResponse<BookRunResponse>(
      rawApi.POST("/api/v1/book-runs/{book_run_id}/resume", {
        params,
        body: {},
      }),
      bookRunSchema,
    );
  },
  listBookRunEvents: (runId: number, signal?: AbortSignal) =>
    parseApiResponse<JobEventPageResponse>(
      rawApi.GET("/api/v1/book-runs/{book_run_id}/events", {
        signal,
        params: {
          path: { book_run_id: runId },
          query: { page: 1, page_size: 500 },
        },
      }),
      jobEventPageSchema,
    ),
  listBookSnapshots: (projectId: number, signal?: AbortSignal) =>
    parseApiResponse<BookSnapshotPageResponse>(
      rawApi.GET("/api/v1/projects/{project_id}/book-snapshots", {
        signal,
        params: { path: { project_id: projectId } },
      }),
      bookSnapshotPageSchema,
    ),
  getBookSnapshot: (snapshotId: number, signal?: AbortSignal) =>
    parseApiResponse<BookSnapshotResponse>(
      rawApi.GET("/api/v1/book-snapshots/{snapshot_id}", {
        signal,
        params: { path: { snapshot_id: snapshotId } },
      }),
      bookSnapshotSchema,
    ),
  getBookEvaluation: (snapshotId: number, signal?: AbortSignal) =>
    parseApiResponse<BookEvaluationResponse>(
      rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/evaluation", {
        signal,
        params: { path: { snapshot_id: snapshotId } },
      }),
      bookEvaluationSchema,
    ),
  getBookTimeline: (snapshotId: number, signal?: AbortSignal) =>
    parseApiResponse<TimelinePageResponse>(
      rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/timeline", {
        signal,
        params: {
          path: { snapshot_id: snapshotId },
          query: { page: 1, page_size: 500 },
        },
      }),
      timelinePageSchema,
    ),
  getBookAnalysis: (
    snapshotId: number,
    kind:
      | "character-arcs"
      | "relationships"
      | "foreshadowing"
      | "pacing"
      | "transitions",
    signal?: AbortSignal,
  ) => {
    const params = { path: { snapshot_id: snapshotId } };
    if (kind === "character-arcs")
      return parseApiResponse<BookAnalysisResponse>(
        rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/character-arcs", {
          signal,
          params,
        }),
        bookAnalysisSchema,
      );
    if (kind === "relationships")
      return parseApiResponse<BookAnalysisResponse>(
        rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/relationships", {
          signal,
          params,
        }),
        bookAnalysisSchema,
      );
    if (kind === "foreshadowing")
      return parseApiResponse<BookAnalysisResponse>(
        rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/foreshadowing", {
          signal,
          params,
        }),
        bookAnalysisSchema,
      );
    if (kind === "pacing")
      return parseApiResponse<BookAnalysisResponse>(
        rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/pacing", {
          signal,
          params,
        }),
        bookAnalysisSchema,
      );
    return parseApiResponse<BookAnalysisResponse>(
      rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/transitions", {
        signal,
        params,
      }),
      bookAnalysisSchema,
    );
  },
  getBookRevisionPlan: (snapshotId: number, signal?: AbortSignal) =>
    parseApiResponse<BookRevisionPlanResponse>(
      rawApi.GET("/api/v1/book-snapshots/{snapshot_id}/revision-plan", {
        signal,
        params: { path: { snapshot_id: snapshotId } },
      }),
      bookRevisionPlanSchema,
    ),
};
