export const queryKeys = {
  health: ["system", "health"] as const,
  readiness: ["system", "readiness"] as const,
  projects: (filters: object = {}) => ["projects", filters] as const,
  project: (projectId: number) => ["project", projectId] as const,
  plan: (projectId: number) => ["project", projectId, "plan"] as const,
  chapters: (projectId: number, filters: object = {}) =>
    ["project", projectId, "chapters", filters] as const,
  chapter: (projectId: number, chapter: number, content = false) =>
    ["project", projectId, "chapter", chapter, { content }] as const,
  context: (projectId: number, chapter: number) =>
    ["project", projectId, "chapter", chapter, "context"] as const,
  versions: (projectId: number, chapter: number) =>
    ["project", projectId, "chapter", chapter, "versions"] as const,
  evaluations: (projectId: number, chapter: number) =>
    ["project", projectId, "chapter", chapter, "evaluations"] as const,
  conflicts: (projectId: number, filters: object = {}) =>
    ["project", projectId, "conflicts", filters] as const,
  facts: (projectId: number) => ["project", projectId, "facts"] as const,
  workflows: (projectId: number) =>
    ["project", projectId, "workflows"] as const,
  workflow: (runId: number) => ["workflow", runId] as const,
  workflowEvents: (runId: number) => ["workflow", runId, "events"] as const,
  workflowUsage: (runId: number) => ["workflow", runId, "usage"] as const,
  memory: (projectId: number, filters: object = {}) =>
    ["project", projectId, "memory", filters] as const,
  memoryStatus: (projectId: number) =>
    ["project", projectId, "memory-status"] as const,
  graphEntities: (projectId: number, search = "") =>
    ["project", projectId, "graph-entities", search] as const,
  graphRelations: (projectId: number, chapter: number) =>
    ["project", projectId, "graph-relations", chapter] as const,
  providers: ["providers"] as const,
  providerHealth: ["providers", "health"] as const,
  usage: (projectId: number) => ["project", projectId, "usage"] as const,
  usageCalls: (projectId: number) =>
    ["project", projectId, "usage", "calls"] as const,
  budget: (projectId: number) => ["project", projectId, "budget"] as const,
  modelSettings: (projectId: number) =>
    ["project", projectId, "model-settings"] as const,
  modelProfiles: ["system", "model-profiles"] as const,
  jobs: (filters: object = {}) => ["jobs", filters] as const,
  job: (jobId: number) => ["job", jobId] as const,
  jobEvents: (jobId: number) => ["job", jobId, "events"] as const,
  bookRuns: (projectId: number) => ["project", projectId, "book-runs"] as const,
  bookRun: (runId: number) => ["book-run", runId] as const,
  bookRunEvents: (runId: number) => ["book-run", runId, "events"] as const,
  bookSnapshots: (projectId: number) =>
    ["project", projectId, "book-snapshots"] as const,
  bookSnapshot: (snapshotId: number) => ["book-snapshot", snapshotId] as const,
  bookAnalysis: (snapshotId: number, kind: string) =>
    ["book-snapshot", snapshotId, kind] as const,
};
