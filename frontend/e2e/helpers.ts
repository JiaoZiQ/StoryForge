import { expect, type APIRequestContext } from "@playwright/test";

type Project = { id: number; title: string };
type Workflow = {
  workflow_run_id: number;
  status: string;
  accepted_version: number | null;
  revision_attempt: number;
};

async function apiJson<T>(
  request: APIRequestContext,
  method: "get" | "post" | "patch",
  path: string,
  data?: unknown,
): Promise<T> {
  const response = await request[method](
    path,
    data === undefined ? {} : { data },
  );
  expect(
    response.ok(),
    `${method.toUpperCase()} ${path}: ${response.status()}`,
  ).toBe(true);
  return (await response.json()) as T;
}

export async function createPlannedProject(
  request: APIRequestContext,
  label: string,
): Promise<Project> {
  const nonce = `${Date.now()}-${Math.random().toString(16).slice(2, 8)}`;
  const project = await apiJson<Project>(
    request,
    "post",
    "/backend/api/v1/projects",
    {
      title: `M9 ${label} ${nonce}`,
      genre: "mystery",
      premise:
        "An archivist follows a brass key through a tidal records network.",
      target_chapters: 3,
      target_words_per_chapter: 300,
      language: "en",
      tone: "restrained",
      audience: "adult",
      additional_requirements: "Keep every clue auditable.",
    },
  );
  await apiJson(
    request,
    "post",
    `/backend/api/v1/projects/${project.id}/plan`,
    { replace_existing: false },
  );
  return project;
}

export async function createAcceptedProject(
  request: APIRequestContext,
  label: string,
): Promise<{ project: Project; workflow: Workflow }> {
  const project = await createPlannedProject(request, label);
  const workflow = await apiJson<Workflow>(
    request,
    "post",
    `/backend/api/v1/projects/${project.id}/chapters/1/workflow`,
    { operation: "generate_evaluate_revise", max_revision_attempts: 2 },
  );
  expect(workflow.status).toBe("completed");
  expect(workflow.accepted_version).not.toBeNull();
  return { project, workflow };
}

export { apiJson };
