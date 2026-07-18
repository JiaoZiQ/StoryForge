"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { storyforgeApi, type ProjectListFilters } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import type {
  ProjectCreateRequest,
  RetrievalSearchRequest,
} from "@/lib/api/types";
import { isWorkflowTerminal } from "@/features/shared/workflow";

export const useProjects = (filters: ProjectListFilters = {}) =>
  useQuery({
    queryKey: queryKeys.projects(filters),
    queryFn: ({ signal }) => storyforgeApi.listProjects(filters, signal),
  });
export const useProject = (id: number) =>
  useQuery({
    queryKey: queryKeys.project(id),
    queryFn: ({ signal }) => storyforgeApi.getProject(id, signal),
    enabled: id > 0,
  });
export const usePlan = (id: number) =>
  useQuery({
    queryKey: queryKeys.plan(id),
    queryFn: ({ signal }) => storyforgeApi.getPlan(id, signal),
    enabled: id > 0,
    retry: false,
  });
export const useChapters = (
  id: number,
  filters: { page?: number; status?: string; hasContent?: boolean } = {},
) =>
  useQuery({
    queryKey: queryKeys.chapters(id, filters),
    queryFn: ({ signal }) => storyforgeApi.listChapters(id, filters, signal),
    enabled: id > 0,
  });
export const useChapter = (id: number, chapter: number, content = false) =>
  useQuery({
    queryKey: queryKeys.chapter(id, chapter, content),
    queryFn: ({ signal }) =>
      storyforgeApi.getChapter(id, chapter, content, signal),
    enabled: id > 0 && chapter > 0,
  });
export const useContext = (id: number, chapter: number, enabled = true) =>
  useQuery({
    queryKey: queryKeys.context(id, chapter),
    queryFn: ({ signal }) => storyforgeApi.getContext(id, chapter, signal),
    enabled: enabled && id > 0 && chapter > 0,
  });
export const useVersions = (id: number, chapter: number) =>
  useQuery({
    queryKey: queryKeys.versions(id, chapter),
    queryFn: ({ signal }) => storyforgeApi.listVersions(id, chapter, signal),
    enabled: id > 0 && chapter > 0,
  });
export const useEvaluations = (id: number, chapter: number) =>
  useQuery({
    queryKey: queryKeys.evaluations(id, chapter),
    queryFn: ({ signal }) => storyforgeApi.listEvaluations(id, chapter, signal),
    enabled: id > 0 && chapter > 0,
  });
export const useConflicts = (
  id: number,
  filters: { severity?: string; status?: string; chapterNumber?: number } = {},
) =>
  useQuery({
    queryKey: queryKeys.conflicts(id, filters),
    queryFn: ({ signal }) => storyforgeApi.listConflicts(id, filters, signal),
    enabled: id > 0,
  });
export const useFacts = (id: number) =>
  useQuery({
    queryKey: queryKeys.facts(id),
    queryFn: ({ signal }) => storyforgeApi.listFacts(id, signal),
    enabled: id > 0,
  });
export const useWorkflows = (id: number) =>
  useQuery({
    queryKey: queryKeys.workflows(id),
    queryFn: ({ signal }) => storyforgeApi.listWorkflows(id, signal),
    enabled: id > 0,
  });
export const useWorkflow = (runId: number) =>
  useQuery({
    queryKey: queryKeys.workflow(runId),
    queryFn: ({ signal }) => storyforgeApi.getWorkflow(runId, signal),
    enabled: runId > 0,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      if (
        isWorkflowTerminal(status) ||
        (typeof document !== "undefined" && document.hidden)
      )
        return false;
      return 3_000;
    },
  });
export const useWorkflowEvents = (runId: number, status?: string) =>
  useQuery({
    queryKey: queryKeys.workflowEvents(runId),
    queryFn: ({ signal }) => storyforgeApi.listWorkflowEvents(runId, signal),
    enabled: runId > 0,
    refetchInterval:
      isWorkflowTerminal(status) ||
      (typeof document !== "undefined" && document.hidden)
        ? false
        : 3_000,
  });
export const useWorkflowUsage = (runId: number, status?: string) =>
  useQuery({
    queryKey: queryKeys.workflowUsage(runId),
    queryFn: ({ signal }) => storyforgeApi.getWorkflowUsage(runId, signal),
    enabled: runId > 0,
    refetchInterval:
      isWorkflowTerminal(status) ||
      (typeof document !== "undefined" && document.hidden)
        ? false
        : 3_000,
  });
export const useMemory = (
  id: number,
  filters: { sourceType?: string; chapterNumber?: number } = {},
) =>
  useQuery({
    queryKey: queryKeys.memory(id, filters),
    queryFn: ({ signal }) => storyforgeApi.listMemory(id, filters, signal),
    enabled: id > 0,
  });
export const useMemoryStatus = (id: number) =>
  useQuery({
    queryKey: queryKeys.memoryStatus(id),
    queryFn: ({ signal }) => storyforgeApi.listMemoryStatus(id, signal),
    enabled: id > 0,
  });
export const useGraphEntities = (id: number, search = "") =>
  useQuery({
    queryKey: queryKeys.graphEntities(id, search),
    queryFn: ({ signal }) =>
      storyforgeApi.listGraphEntities(id, search, signal),
    enabled: id > 0,
  });
export const useGraphRelations = (id: number, chapter: number) =>
  useQuery({
    queryKey: queryKeys.graphRelations(id, chapter),
    queryFn: ({ signal }) =>
      storyforgeApi.listGraphRelations(id, chapter, signal),
    enabled: id > 0 && chapter > 0,
  });
export const useProviders = () =>
  useQuery({
    queryKey: queryKeys.providers,
    queryFn: ({ signal }) => storyforgeApi.listProviders(signal),
  });
export const useProviderHealth = () =>
  useQuery({
    queryKey: queryKeys.providerHealth,
    queryFn: ({ signal }) => storyforgeApi.providerHealth(signal),
  });
export const useUsage = (id: number) =>
  useQuery({
    queryKey: queryKeys.usage(id),
    queryFn: ({ signal }) => storyforgeApi.getUsage(id, signal),
    enabled: id > 0,
  });
export const useUsageCalls = (id: number) =>
  useQuery({
    queryKey: queryKeys.usageCalls(id),
    queryFn: ({ signal }) => storyforgeApi.listUsageCalls(id, signal),
    enabled: id > 0,
  });
export const useBudget = (id: number) =>
  useQuery({
    queryKey: queryKeys.budget(id),
    queryFn: ({ signal }) => storyforgeApi.getBudget(id, signal),
    enabled: id > 0,
  });
export const useModelSettings = (id: number) =>
  useQuery({
    queryKey: queryKeys.modelSettings(id),
    queryFn: ({ signal }) => storyforgeApi.getModelSettings(id, signal),
    enabled: id > 0,
  });
export const useModelProfiles = () =>
  useQuery({
    queryKey: queryKeys.modelProfiles,
    queryFn: ({ signal }) => storyforgeApi.listModelProfiles(signal),
  });

export function useCreateProject() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: ProjectCreateRequest) =>
      storyforgeApi.createProject(body),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: ["projects"] });
    },
  });
}
export function useGeneratePlan(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (replace: boolean) =>
      storyforgeApi.generatePlan(projectId, replace),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.project(projectId) }),
        client.invalidateQueries({ queryKey: queryKeys.plan(projectId) }),
        client.invalidateQueries({
          queryKey: ["project", projectId, "chapters"],
        }),
      ]);
    },
  });
}
export function useGenerateChapter(projectId: number, chapter: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => storyforgeApi.generateChapter(projectId, chapter),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: ["project", projectId, "chapter", chapter],
      });
    },
  });
}
export function useStartWorkflow(projectId: number, chapter: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => storyforgeApi.startWorkflow(projectId, chapter),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["project", projectId, "chapter", chapter],
        }),
        client.invalidateQueries({ queryKey: queryKeys.workflows(projectId) }),
      ]);
    },
  });
}
export function useUpdateConflict(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({
      id,
      status,
      note,
    }: {
      id: number;
      status: "open" | "resolved" | "ignored" | "false_positive";
      note?: string;
    }) => storyforgeApi.updateConflict(projectId, id, status, note),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: ["project", projectId, "conflicts"],
      });
    },
  });
}
export function useReindexMemory(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: () => storyforgeApi.reindexMemory(projectId),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({
          queryKey: ["project", projectId, "memory"],
        }),
        client.invalidateQueries({
          queryKey: queryKeys.memoryStatus(projectId),
        }),
      ]);
    },
  });
}
export function useRetrieval(projectId: number) {
  return useMutation({
    mutationFn: (body: RetrievalSearchRequest) =>
      storyforgeApi.searchMemory(projectId, body),
  });
}
export function useSetBudget(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (body: {
      currency: string;
      soft_limit: string;
      hard_limit: string;
      period: "lifetime" | "daily" | "monthly";
      enabled: boolean;
    }) => storyforgeApi.setBudget(projectId, body),
    onSuccess: async () => {
      await client.invalidateQueries({ queryKey: queryKeys.budget(projectId) });
    },
  });
}
export function useSetModelProfile(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (profile: "offline" | "economy" | "balanced" | "quality") =>
      storyforgeApi.setModelProfile(projectId, profile),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: queryKeys.modelSettings(projectId),
      });
    },
  });
}
export function useSetPrivacyPolicy(projectId: number) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: (policy: "offline" | "strict" | "standard") =>
      storyforgeApi.setPrivacyPolicy(projectId, policy),
    onSuccess: async () => {
      await client.invalidateQueries({
        queryKey: queryKeys.modelSettings(projectId),
      });
    },
  });
}
