import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import {
  ApiErrorAlert,
  ConfirmDialog,
  EmptyState,
  ErrorState,
  InlineLoading,
  PageLoading,
  Pagination,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { ApiClientError } from "@/lib/api/errors";

describe("shared UI states", () => {
  it("renders loading, empty, status and score states accessibly", () => {
    const { rerender } = render(<PageLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading StoryForge");
    rerender(<InlineLoading />);
    expect(screen.getByRole("status")).toHaveTextContent("Working");
    rerender(<EmptyState title="Nothing here" message="Create one first" />);
    expect(screen.getByRole("heading", { name: "Nothing here" })).toBeVisible();
    rerender(<StatusBadge value="completed_needs_review" />);
    expect(screen.getByText(/Completed Needs Review/)).toBeVisible();
    rerender(<ScoreBadge score={7.5} />);
    expect(screen.getByLabelText("Score 7.50 out of 10")).toBeVisible();
    rerender(<ScoreBadge score={null} />);
    expect(screen.getByLabelText("No score")).toBeVisible();
  });

  it("shows safe API details and retries", async () => {
    const retry = vi.fn();
    const error = new ApiClientError(
      404,
      { error: "not_found", message: "Missing", details: [] },
      "req-safe",
    );
    const { rerender } = render(<ErrorState error={error} retry={retry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Missing");
    expect(screen.getByText("req-safe")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(retry).toHaveBeenCalledOnce();
    rerender(<ApiErrorAlert error="bad" />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "StoryForge could not complete the request",
    );
  });

  it("focuses and dismisses the confirmation dialog", async () => {
    const cancel = vi.fn();
    const confirm = vi.fn();
    render(
      <ConfirmDialog
        open
        title="Replace plan?"
        message="Existing chapters remain auditable."
        onCancel={cancel}
        onConfirm={confirm}
      />,
    );
    expect(screen.getByRole("dialog")).toBeVisible();
    expect(screen.getByRole("button", { name: "Cancel" })).toHaveFocus();
    await userEvent.keyboard("{Escape}");
    expect(cancel).toHaveBeenCalledOnce();
    await userEvent.click(screen.getByRole("button", { name: "Confirm" }));
    expect(confirm).toHaveBeenCalledOnce();
  });

  it("enforces pagination boundaries", async () => {
    const onPage = vi.fn();
    const { rerender } = render(
      <Pagination page={1} totalPages={3} onPage={onPage} />,
    );
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenCalledWith(2);
    rerender(<Pagination page={3} totalPages={3} onPage={onPage} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });
});
