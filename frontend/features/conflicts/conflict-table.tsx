"use client";

import { useState } from "react";
import { useUpdateConflict } from "@/hooks/use-storyforge";
import type { ConflictResponse } from "@/lib/api/types";
import { ApiErrorAlert, EmptyState, StatusBadge } from "@/components/ui/states";
import { clipText, humanize } from "@/lib/formatting";

export function ConflictTable({
  projectId,
  conflicts,
}: {
  projectId: number;
  conflicts: ConflictResponse[];
}) {
  const mutation = useUpdateConflict(projectId);
  const [optimistic, setOptimistic] = useState<Record<number, string>>({});
  const [notes, setNotes] = useState<Record<number, string>>({});
  if (!conflicts.length)
    return (
      <EmptyState
        title="No conflicts"
        message="No consistency conflicts match the current filter."
      />
    );
  const update = async (
    conflict: ConflictResponse,
    status: "open" | "resolved" | "ignored" | "false_positive",
  ) => {
    const previous = optimistic[conflict.id];
    setOptimistic((values) => ({ ...values, [conflict.id]: status }));
    try {
      await mutation.mutateAsync({
        id: conflict.id,
        status,
        note: status === "resolved" ? notes[conflict.id] : undefined,
      });
      setOptimistic((values) => {
        const copy = { ...values };
        delete copy[conflict.id];
        return copy;
      });
    } catch {
      setOptimistic((values) => ({
        ...values,
        [conflict.id]: previous ?? conflict.status,
      }));
    }
  };
  return (
    <div>
      {mutation.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={mutation.error} />
        </div>
      ) : null}
      <div className="grid gap-4">
        {conflicts.map((conflict) => {
          const status = optimistic[conflict.id] ?? conflict.status;
          return (
            <article
              className={`rounded-xl border p-5 ${["critical", "high"].includes(conflict.severity) ? "border-red-700/30 bg-red-50" : "border-black/10 bg-white"}`}
              key={conflict.id}
            >
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
                    Chapter version {conflict.chapter_version_id} ·{" "}
                    {humanize(conflict.conflict_type)}
                  </p>
                  <h3 className="mt-1 font-bold">{conflict.subject}</h3>
                </div>
                <div className="flex gap-2">
                  <StatusBadge value={conflict.severity} />
                  <StatusBadge value={status} />
                </div>
              </div>
              <p className="mt-3">{conflict.description}</p>
              <details className="mt-3 text-sm">
                <summary className="font-semibold">
                  Evidence and resolution
                </summary>
                <blockquote className="mt-2 border-l-4 border-black/15 pl-3 text-ink-600">
                  {clipText(conflict.new_evidence, 500)}
                </blockquote>
                {conflict.existing_evidence ? (
                  <blockquote className="mt-2 border-l-4 border-black/15 pl-3 text-ink-600">
                    Existing: {clipText(conflict.existing_evidence, 500)}
                  </blockquote>
                ) : null}
                <p className="mt-2">
                  <strong>Suggested:</strong> {conflict.suggested_resolution}
                </p>
              </details>
              <div className="mt-4 grid gap-3 md:grid-cols-[1fr_auto]">
                <label className="label">
                  Resolution note
                  <input
                    className="field"
                    value={notes[conflict.id] ?? conflict.resolution_note ?? ""}
                    onChange={(event) =>
                      setNotes((values) => ({
                        ...values,
                        [conflict.id]: event.target.value,
                      }))
                    }
                    disabled={mutation.isPending}
                  />
                </label>
                <div className="flex flex-wrap items-end gap-2">
                  {(
                    ["open", "resolved", "ignored", "false_positive"] as const
                  ).map((value) => (
                    <button
                      className={
                        value === "resolved"
                          ? "button-primary"
                          : "button-secondary"
                      }
                      key={value}
                      type="button"
                      disabled={mutation.isPending || value === status}
                      onClick={() => void update(conflict, value)}
                    >
                      {humanize(value)}
                    </button>
                  ))}
                </div>
              </div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
