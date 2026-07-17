"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { ApiClientError } from "@/lib/api/errors";
import { humanize } from "@/lib/formatting";

export function PageLoading({
  label = "Loading StoryForge data…",
}: {
  label?: string;
}) {
  return (
    <div
      className="surface rounded-xl p-8 text-ink-600"
      role="status"
      aria-live="polite"
    >
      {label}
    </div>
  );
}
export function InlineLoading({ label = "Working…" }: { label?: string }) {
  return (
    <span role="status" aria-live="polite" className="text-sm text-ink-600">
      {label}
    </span>
  );
}
export function EmptyState({
  title,
  message,
  action,
}: {
  title: string;
  message: string;
  action?: ReactNode;
}) {
  return (
    <section className="surface rounded-xl p-8 text-center">
      <h2 className="text-lg font-bold">{title}</h2>
      <p className="mx-auto mt-2 max-w-xl text-ink-600">{message}</p>
      {action ? <div className="mt-5">{action}</div> : null}
    </section>
  );
}
export function ErrorState({
  error,
  retry,
}: {
  error: unknown;
  retry?: () => void;
}) {
  return (
    <ApiErrorAlert
      error={error}
      action={
        retry ? (
          <button className="button-secondary" type="button" onClick={retry}>
            Try again
          </button>
        ) : undefined
      }
    />
  );
}
export function ApiErrorAlert({
  error,
  action,
}: {
  error: unknown;
  action?: ReactNode;
}) {
  const apiError = error instanceof ApiClientError ? error : null;
  return (
    <section
      role="alert"
      className="rounded-lg border border-red-700/25 bg-red-50 p-4 text-red-950"
    >
      <p className="font-bold">
        {apiError ? humanize(apiError.code) : "Request failed"}
      </p>
      <p className="mt-1 text-sm">
        {error instanceof Error
          ? error.message
          : "StoryForge could not complete the request."}
      </p>
      {apiError?.requestId ? (
        <details className="mt-2 text-xs">
          <summary>Request ID</summary>
          <code>{apiError.requestId}</code>
        </details>
      ) : null}
      {action ? <div className="mt-3">{action}</div> : null}
    </section>
  );
}
export function StatusBadge({ value }: { value: string }) {
  const severe = [
    "failed",
    "critical",
    "rejected",
    "evaluation_failed",
    "workflow_failed",
  ].some((part) => value.includes(part));
  const good = [
    "accepted",
    "completed",
    "passed",
    "ready",
    "ok",
    "resolved",
  ].some((part) => value.includes(part));
  return (
    <span
      className={`inline-flex rounded-full border px-2.5 py-1 text-xs font-bold ${severe ? "border-red-700/25 bg-red-50 text-red-900" : good ? "border-teal/25 bg-emerald-50 text-teal-dark" : "border-amber-700/25 bg-amber-50 text-amber-900"}`}
    >
      <span className="sr-only">Status: </span>
      {humanize(value)}
    </span>
  );
}
export function ScoreBadge({ score }: { score: number | null | undefined }) {
  const value = score ?? 0;
  return (
    <span
      className={`inline-flex min-w-14 justify-center rounded px-2 py-1 font-mono text-sm font-bold ${score == null ? "bg-black/5" : value >= 7 ? "bg-emerald-100 text-teal-dark" : value >= 5 ? "bg-amber-100 text-amber-900" : "bg-red-100 text-red-900"}`}
      aria-label={
        score == null ? "No score" : `Score ${score.toFixed(2)} out of 10`
      }
    >
      {score == null ? "—" : score.toFixed(2)}
    </span>
  );
}

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel = "Confirm",
  onConfirm,
  onCancel,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel?: string;
  onConfirm: () => void;
  onCancel: () => void;
}) {
  const cancelRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (open) cancelRef.current?.focus();
  }, [open]);
  useEffect(() => {
    const listener = (event: KeyboardEvent) => {
      if (open && event.key === "Escape") onCancel();
    };
    window.addEventListener("keydown", listener);
    return () => window.removeEventListener("keydown", listener);
  }, [open, onCancel]);
  if (!open) return null;
  return (
    <div
      className="fixed inset-0 z-50 grid place-items-center bg-black/45 p-4"
      role="presentation"
    >
      <section
        role="dialog"
        aria-modal="true"
        aria-labelledby="confirm-title"
        className="w-full max-w-md rounded-xl bg-white p-6 shadow-2xl"
      >
        <h2 id="confirm-title" className="text-xl font-bold">
          {title}
        </h2>
        <p className="mt-3 text-ink-600">{message}</p>
        <div className="mt-6 flex justify-end gap-3">
          <button
            ref={cancelRef}
            type="button"
            className="button-secondary"
            onClick={onCancel}
          >
            Cancel
          </button>
          <button type="button" className="button-primary" onClick={onConfirm}>
            {confirmLabel}
          </button>
        </div>
      </section>
    </div>
  );
}

export function Pagination({
  page,
  totalPages,
  onPage,
}: {
  page: number;
  totalPages: number;
  onPage: (page: number) => void;
}) {
  return (
    <nav
      aria-label="Pagination"
      className="mt-5 flex items-center justify-between"
    >
      <button
        className="button-secondary"
        type="button"
        disabled={page <= 1}
        onClick={() => onPage(page - 1)}
      >
        Previous
      </button>
      <span className="text-sm text-ink-600">
        Page {page} of {Math.max(totalPages, 1)}
      </span>
      <button
        className="button-secondary"
        type="button"
        disabled={page >= totalPages}
        onClick={() => onPage(page + 1)}
      >
        Next
      </button>
    </nav>
  );
}
