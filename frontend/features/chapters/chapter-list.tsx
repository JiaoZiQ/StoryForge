"use client";

import Link from "next/link";
import { useState } from "react";
import { useChapters } from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";

export function ChapterList({ projectId }: { projectId: number }) {
  const [status, setStatus] = useState("");
  const [content, setContent] = useState("");
  const query = useChapters(projectId, {
    status: status || undefined,
    hasContent: content === "yes" ? true : content === "no" ? false : undefined,
  });
  return (
    <>
      <PageHeader
        eyebrow="Manuscript"
        title="Chapters"
        description="Metadata-only chapter overview. Full prose is requested only from an individual Content tab."
      />
      <form
        className="surface mb-5 grid gap-3 rounded-xl p-4 sm:grid-cols-2"
        aria-label="Chapter filters"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="label">
          Status
          <select
            className="field"
            value={status}
            onChange={(event) => setStatus(event.target.value)}
          >
            <option value="">All statuses</option>
            {[
              "planned",
              "generated",
              "workflow_running",
              "accepted",
              "needs_review",
              "workflow_failed",
            ].map((value) => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label className="label">
          Content
          <select
            className="field"
            value={content}
            onChange={(event) => setContent(event.target.value)}
          >
            <option value="">Any</option>
            <option value="yes">Has content</option>
            <option value="no">No content</option>
          </select>
        </label>
      </form>
      {query.isLoading ? (
        <PageLoading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data!.items.length === 0 ? (
        <EmptyState
          title="No chapters"
          message="Generate a plan first, or adjust the chapter filters."
        />
      ) : (
        <section className="surface rounded-xl p-4">
          <div className="table-wrap">
            <table>
              <caption>Planned and generated chapters</caption>
              <thead>
                <tr>
                  <th>Chapter</th>
                  <th>Status</th>
                  <th>Current</th>
                  <th>Accepted</th>
                  <th>Score</th>
                  <th>Content</th>
                </tr>
              </thead>
              <tbody>
                {query.data!.items.map((chapter) => (
                  <tr key={chapter.id}>
                    <td>
                      <Link
                        className="font-bold text-copper-dark hover:underline"
                        href={`/projects/${projectId}/chapters/${chapter.chapter_number}`}
                      >
                        {chapter.chapter_number}. {chapter.title}
                      </Link>
                      <p className="mt-1 text-sm text-ink-600">
                        {chapter.objective}
                      </p>
                    </td>
                    <td>
                      <StatusBadge value={chapter.status} />
                    </td>
                    <td>{chapter.current_version_id ?? "—"}</td>
                    <td>{chapter.accepted_version_id ?? "—"}</td>
                    <td>
                      <ScoreBadge score={chapter.score} />
                    </td>
                    <td>
                      {chapter.has_content ? "Available" : "Not generated"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}
