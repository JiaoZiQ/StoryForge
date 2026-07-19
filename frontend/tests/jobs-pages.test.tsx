import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { JobCenter } from "@/features/jobs/job-center";
import { JobDetail } from "@/features/jobs/job-detail";

const api = vi.hoisted(() => ({
  listJobs: vi.fn(),
  getJob: vi.fn(),
  listJobEvents: vi.fn(),
  controlJob: vi.fn(),
  queueHealth: vi.fn(),
}));

vi.mock("@/lib/api/storyforge", () => ({ storyforgeApi: api }));

const job = {
  id: 41,
  job_type: "run_chapter_workflow",
  status: "running",
  project_id: 7,
  chapter_id: 9,
  chapter_number: 1,
  workflow_run_id: null,
  queue_name: "workflow",
  priority: 0,
  progress: 45,
  current_step: "evaluate_draft",
  attempt: 1,
  max_attempts: 3,
  available_at: "2026-07-18T00:00:00Z",
  queued_at: "2026-07-18T00:00:00Z",
  started_at: "2026-07-18T00:00:00Z",
  finished_at: null,
  error_code: null,
  error_message: null,
  result: {},
  worker_id: "worker-safe",
  correlation_id: "correlation-safe",
  created_at: "2026-07-18T00:00:00Z",
  updated_at: "2026-07-18T00:00:00Z",
};

function wrapper({ children }: { children: ReactNode }) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

beforeEach(() => {
  api.listJobs.mockResolvedValue({
    items: [job],
    page: 1,
    page_size: 100,
    total_items: 1,
    total_pages: 1,
  });
  api.getJob.mockResolvedValue(job);
  api.listJobEvents.mockResolvedValue({
    items: [
      {
        id: 2,
        sequence: 2,
        event_type: "workflow_node_completed",
        status: "running",
        step: "evaluate_draft",
        progress: 45,
        message_code: "workflow.node_completed",
        message: "Workflow node completed",
        attempt: 1,
        worker_id: "worker-safe",
        created_at: "2026-07-18T00:00:00Z",
      },
    ],
    page: 1,
    page_size: 100,
    total_items: 1,
    total_pages: 1,
  });
  api.controlJob.mockResolvedValue({ ...job, status: "pause_requested" });
  api.queueHealth.mockResolvedValue({
    mode: "queue",
    broker_reachable: true,
    pending_jobs: 1,
    soft_limit_exceeded: false,
    pending_soft_limit: 100,
    pending_hard_limit: 500,
    project_pending_limit: 25,
    workers: [{ worker_id: "worker-safe" }],
  });
});

describe("asynchronous job pages", () => {
  it("renders a content-free job list", async () => {
    render(<JobCenter />, { wrapper });
    expect(
      await screen.findByRole("heading", { name: "Job Center" }),
    ).toBeVisible();
    expect(screen.getByRole("link", { name: "#41" })).toHaveAttribute(
      "href",
      "/jobs/41",
    );
    expect(screen.getByText("45%")).toBeVisible();
    expect(document.body.textContent).not.toMatch(/sk-[A-Za-z0-9_-]{12,}/);
  });

  it("shows progress events and sends a cooperative pause", async () => {
    render(<JobDetail jobId={41} />, { wrapper });
    expect(
      await screen.findByRole("heading", { name: "Job #41" }),
    ).toBeVisible();
    expect(screen.getByText("Workflow node completed")).toBeVisible();
    await userEvent.click(screen.getByRole("button", { name: "Pause" }));
    await waitFor(() =>
      expect(api.controlJob).toHaveBeenCalledWith(41, "pause"),
    );
  });
});
