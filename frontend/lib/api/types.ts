import type { components } from "./generated";

export type PageMeta = components["schemas"]["PageMeta"];
export type Page<T> = { items: T[]; meta: PageMeta };
export type ProjectSummary = components["schemas"]["ProjectSummary"];
export type ProjectDetail = components["schemas"]["ProjectDetail"];
export type ProjectCreateRequest =
  components["schemas"]["ProjectCreateRequest"];
export type PlanResponse = components["schemas"]["PlanResponse"];
export type ChapterSummary = components["schemas"]["ChapterSummary"];
export type ChapterDetail = components["schemas"]["ChapterDetail"];
export type ContextSummary = components["schemas"]["ContextSummary"];
export type ChapterGenerationResponse =
  components["schemas"]["ChapterGenerationResponse"];
export type VersionSummary = components["schemas"]["VersionSummary"];
export type VersionDetail = components["schemas"]["VersionDetail"];
export type VersionDiffResponse = components["schemas"]["VersionDiffResponse"];
export type EvaluationSummary = components["schemas"]["EvaluationSummary"];
export type EvaluationDetail = components["schemas"]["EvaluationDetail"];
export type ConflictResponse = components["schemas"]["ConflictResponse"];
export type FactResponse = components["schemas"]["FactResponse"];
export type WorkflowStatusResponse =
  components["schemas"]["WorkflowStatusResponse"];
export type WorkflowEventResponse =
  components["schemas"]["WorkflowEventResponse"];
export type RetrievalSearchRequest =
  components["schemas"]["RetrievalSearchRequest"];
export type RetrievalSearchResponse =
  components["schemas"]["RetrievalSearchResponse"];
export type MemorySummary = components["schemas"]["MemorySummary"];
export type MemoryDetail = components["schemas"]["MemoryDetail"];
export type MemoryIndexStatusResponse =
  components["schemas"]["MemoryIndexStatusResponse"];
export type MemoryReindexResponse =
  components["schemas"]["MemoryReindexResponse"];
export type GraphEntityResponse = components["schemas"]["GraphEntityResponse"];
export type GraphRelationResponse =
  components["schemas"]["GraphRelationResponse"];
export type GraphNeighborsResponse =
  components["schemas"]["GraphNeighborsResponse"];
export type HealthResponse = components["schemas"]["HealthResponse"];
export type ReadinessResponse = components["schemas"]["ReadinessResponse"];
export type ProviderCapabilityResponse =
  components["schemas"]["ProviderCapabilityResponse"];
export type ProviderHealthResponse =
  components["schemas"]["ProviderHealthResponse"];
export type ProviderCallResponse =
  components["schemas"]["ProviderCallResponse"];
export type UsageSummaryResponse =
  components["schemas"]["UsageSummaryResponse"];
export type ProjectBudgetResponse =
  components["schemas"]["ProjectBudgetResponse"];
export type ProjectModelSettingsResponse =
  components["schemas"]["ProjectModelSettingsResponse"];
export type ModelProfileOption = components["schemas"]["ModelProfileOption"];
export type JobResponse = components["schemas"]["JobResponse"];
export type JobAcceptedResponse = components["schemas"]["JobAcceptedResponse"];
export type JobCreateRequest = components["schemas"]["JobCreateRequest"];
export type JobEventResponse = components["schemas"]["JobEventResponse"];
export type JobPageResponse = components["schemas"]["JobPageResponse"];
export type JobEventPageResponse =
  components["schemas"]["JobEventPageResponse"];
export type QueueHealthResponse = components["schemas"]["QueueHealthResponse"];
export type BookRunCreateRequest =
  components["schemas"]["BookRunCreateRequest"];
export type BookRunAcceptedResponse =
  components["schemas"]["BookRunAcceptedResponse"];
export type BookRunResponse = components["schemas"]["BookRunResponse"];
export type BookRunPageResponse = components["schemas"]["BookRunPageResponse"];
export type BookSnapshotResponse =
  components["schemas"]["BookSnapshotResponse"];
export type BookSnapshotPageResponse =
  components["schemas"]["BookSnapshotPageResponse"];
export type BookEvaluationResponse =
  components["schemas"]["BookEvaluationResponse"];
export type BookAnalysisResponse =
  components["schemas"]["BookAnalysisResponse"];
export type TimelinePageResponse =
  components["schemas"]["TimelinePageResponse"];
export type BookRevisionPlanResponse =
  components["schemas"]["BookRevisionPlanResponse"];
