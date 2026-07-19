import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactElement } from "react";
import { BookRunsPage } from "@/features/books/book-runs-page";
import { BookRunWorkspace } from "@/features/books/book-run-workspace";

const hooks = vi.hoisted(() => ({
  useBookRuns: vi.fn(),
  useCreateBookRun: vi.fn(),
  useBookRun: vi.fn(),
  useBookRunEvents: vi.fn(),
  useBookSnapshots: vi.fn(),
  useBookEvaluation: vi.fn(),
  useBookTimeline: vi.fn(),
  useBookAnalysis: vi.fn(),
  useBookRevisionPlan: vi.fn(),
  useControlBookRun: vi.fn(),
}));

vi.mock("@/hooks/use-storyforge", () => hooks);
vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

const ready = <T,>(data: T) => ({
  data,
  isLoading: false,
  error: null,
  refetch: vi.fn(),
});
const mutation = () => ({ mutate: vi.fn(), isPending: false, error: null });
const renderWithClient = (value: ReactElement) =>
  render(
    <QueryClientProvider client={new QueryClient()}>
      {value}
    </QueryClientProvider>,
  );

const run = {
  id: 1,
  project_id: 1,
  job_id: 2,
  status: "completed",
  mode: "sequential",
  total_chapters: 5,
  completed_chapters: 5,
  accepted_chapters: 5,
  failed_chapters: 0,
  needs_review_chapters: 0,
  current_chapter_number: 5,
  current_global_revision_round: 1,
  max_global_revision_rounds: 2,
  current_node: "accept_book_snapshot",
  progress: 100,
  book_snapshot_id: 10,
  best_snapshot_id: 10,
  blocking_reasons: [],
  chapter_status: {
    "1": "accepted",
    "2": "accepted",
    "3": "accepted",
    "4": "accepted",
    "5": "accepted",
  },
  periodic_checks: [],
  spent_cost: "0",
  remaining_cost: "5",
  used_tokens: 100,
  remaining_tokens: 999900,
  provider_calls: 5,
  remaining_provider_calls: 245,
  started_at: "2026-07-19T00:00:00Z",
  updated_at: "2026-07-19T00:01:00Z",
  finished_at: "2026-07-19T00:01:00Z",
  error_code: null,
  error_message: null,
} as const;

beforeEach(() => {
  hooks.useBookRuns.mockReturnValue(
    ready({
      items: [run],
      page: 1,
      page_size: 20,
      total_items: 1,
      total_pages: 1,
    }),
  );
  hooks.useCreateBookRun.mockReturnValue(mutation());
  hooks.useBookRun.mockReturnValue(ready(run));
  hooks.useBookRunEvents.mockReturnValue(
    ready({
      items: [
        {
          id: 1,
          message: "Workflow completed",
          status: "succeeded",
          step: "completed",
          progress: 100,
        },
      ],
      page: 1,
      page_size: 100,
      total_items: 1,
    }),
  );
  hooks.useBookSnapshots.mockReturnValue(
    ready({
      items: [
        {
          id: 10,
          project_id: 1,
          book_run_id: 1,
          snapshot_number: 2,
          status: "accepted",
          chapter_version_map: { "1": 11, "2": 12, "3": 13, "4": 14, "5": 15 },
          total_words: 2000,
          chapter_count: 5,
          accepted_chapter_count: 5,
          content_hash: "hash",
          evaluation_summary: {},
          created_at: "2026-07-19T00:01:00Z",
          accepted_at: "2026-07-19T00:01:00Z",
        },
      ],
      total_items: 1,
    }),
  );
  hooks.useBookEvaluation.mockReturnValue(
    ready({
      id: 1,
      book_snapshot_id: 10,
      evaluation_version: 2,
      final_score: 8.7,
      passed: true,
      dimension_scores: { timeline: 9 },
      blocking_reasons: [],
      recommended_action: "accept",
      priority_chapters: [],
      global_issues: [],
      evaluator_versions: {},
      prompt_versions: {},
      created_at: "2026-07-19T00:01:00Z",
    }),
  );
  hooks.useBookTimeline.mockReturnValue(
    ready({
      items: [{ event_key: "event", chapter_number: 1, title: "Clue" }],
      page: 1,
      page_size: 100,
      total_items: 1,
      total_pages: 1,
    }),
  );
  hooks.useBookAnalysis.mockImplementation((_id: number, kind: string) =>
    ready({
      snapshot_id: 10,
      kind,
      score: 8.5,
      summary: { count: 1 },
      items: [{ chapter_number: 1, score: 8.5, evidence: "accepted summary" }],
    }),
  );
  hooks.useBookRevisionPlan.mockReturnValue(ready(undefined));
  hooks.useControlBookRun.mockReturnValue(mutation());
});

describe("whole-book pages", () => {
  it("renders durable run history without manuscript content", () => {
    renderWithClient(<BookRunsPage projectId={1} />);
    expect(screen.getByRole("heading", { name: "Book runs" })).toBeVisible();
    expect(screen.getByRole("link", { name: "#1" })).toHaveAttribute(
      "href",
      "/projects/1/book/1",
    );
    expect(document.body.textContent).not.toContain("chapter body");
  });

  it("supports keyboard-accessible global analysis tabs and text alternatives", async () => {
    const user = userEvent.setup();
    renderWithClient(<BookRunWorkspace projectId={1} runId={1} />);
    expect(screen.getByRole("heading", { name: "Book run #1" })).toBeVisible();
    expect(screen.getByText("Workflow completed")).toBeVisible();
    const pacing = screen.getByRole("tab", { name: "Pacing" });
    await user.click(pacing);
    expect(pacing).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("heading", { name: "Pacing" })).toBeVisible();
    expect(screen.getByText("accepted summary")).toBeVisible();
    await user.click(screen.getByRole("tab", { name: "Global evaluation" }));
    expect(screen.getByText("Priority chapters: none")).toBeVisible();
  });
});
