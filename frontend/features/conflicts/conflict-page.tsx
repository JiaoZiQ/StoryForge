"use client";

import { useState } from "react";
import { useConflicts } from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import { ErrorState, PageLoading } from "@/components/ui/states";
import { ConflictTable } from "./conflict-table";

export function ConflictPage({ projectId }: { projectId: number }) {
  const [severity, setSeverity] = useState("");
  const [status, setStatus] = useState("");
  const [chapter, setChapter] = useState("");
  const query = useConflicts(projectId, {
    severity: severity || undefined,
    status: status || undefined,
    chapterNumber: chapter ? Number(chapter) : undefined,
  });
  return (
    <>
      <PageHeader
        eyebrow="Consistency"
        title="Conflicts"
        description="Review immutable evidence and update only the conflict lifecycle status."
      />
      <form
        className="surface mb-5 grid gap-3 rounded-xl p-4 sm:grid-cols-3"
        aria-label="Conflict filters"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="label">
          Severity
          <select
            className="field"
            value={severity}
            onChange={(event) => setSeverity(event.target.value)}
          >
            <option value="">All severities</option>
            {["critical", "high", "medium", "low"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="label">
          Status
          <select
            className="field"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {["open", "resolved", "ignored", "false_positive"].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="label">
          Chapter
          <input
            className="field"
            type="number"
            min="1"
            value={chapter}
            onChange={(event) => setChapter(event.target.value)}
          />
        </label>
      </form>
      {query.isLoading ? (
        <PageLoading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : (
        <ConflictTable projectId={projectId} conflicts={query.data!.items} />
      )}
    </>
  );
}
