"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  useMemory,
  useMemoryStatus,
  useReindexMemory,
} from "@/hooks/use-storyforge";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  ApiErrorAlert,
  EmptyState,
  ErrorState,
  InlineLoading,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function MemoryPage({ projectId }: { projectId: number }) {
  const [sourceType, setSourceType] = useState("");
  const [chapter, setChapter] = useState("");
  const chunks = useMemory(projectId, {
    sourceType: sourceType || undefined,
    chapterNumber: chapter ? Number(chapter) : undefined,
  });
  const status = useMemoryStatus(projectId);
  const reindex = useReindexMemory(projectId);
  const router = useRouter();
  const totalChunks =
    status.data?.items.reduce((sum, item) => sum + item.chunk_count, 0) ?? 0;
  return (
    <>
      <PageHeader
        eyebrow="Long-term memory"
        title="Memory index"
        description="Accepted, past-only chunks with provider metadata. Embedding arrays are never returned."
        actions={
          <button
            className="button-primary"
            type="button"
            disabled={reindex.isPending}
            onClick={() =>
              void reindex
                .mutateAsync()
                .then((job) => router.push(`/jobs/${job.job_id}`))
            }
          >
            {reindex.isPending ? "Reindexing…" : "Reindex accepted chapters"}
          </button>
        }
      />
      {reindex.isPending ? (
        <div className="mb-4">
          <InlineLoading label="Creating a durable indexing job…" />
        </div>
      ) : null}
      {reindex.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={reindex.error} />
        </div>
      ) : null}
      {reindex.data ? (
        <section
          role="status"
          className="mb-5 rounded-lg border border-teal/20 bg-emerald-50 p-4 text-teal-dark"
        >
          Reindex job #{reindex.data.job_id} was accepted. Opening Job Center…
        </section>
      ) : null}
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Accepted chunks" value={totalChunks} />
        <StatCard
          label="Index records"
          value={status.data?.meta.total_items ?? "—"}
        />
        <StatCard
          label="Failed indexes"
          value={
            status.data?.items.filter((item) => item.status === "failed")
              .length ?? "—"
          }
        />
      </div>
      <div className="grid gap-6">
        <Section title="Index status">
          {status.isLoading ? (
            <PageLoading />
          ) : status.error ? (
            <ErrorState error={status.error} />
          ) : status.data!.items.length ? (
            <div className="table-wrap">
              <table>
                <caption>Accepted version indexing attempts</caption>
                <thead>
                  <tr>
                    <th>Version</th>
                    <th>Status</th>
                    <th>Attempt</th>
                    <th>Chunks</th>
                    <th>Graph</th>
                    <th>Embedding</th>
                  </tr>
                </thead>
                <tbody>
                  {status.data!.items.map((item) => (
                    <tr key={item.id}>
                      <td>{item.chapter_version_id}</td>
                      <td>
                        <StatusBadge value={item.status} />
                      </td>
                      <td>{item.attempt_count}</td>
                      <td>{item.chunk_count}</td>
                      <td>
                        {item.graph_entity_count} entities /{" "}
                        {item.graph_relation_count} relations
                      </td>
                      <td>
                        {item.embedding_provider} / {item.embedding_model} (
                        {item.embedding_dimensions}D)
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No index records"
              message="Accept a chapter version or run reindex after a workflow completes."
            />
          )}
        </Section>
        <Section title="Accepted chunks">
          <form
            className="mb-4 grid gap-3 sm:grid-cols-2"
            aria-label="Memory filters"
            onSubmit={(event) => event.preventDefault()}
          >
            <label className="label">
              Source type
              <input
                className="field"
                value={sourceType}
                onChange={(event) => setSourceType(event.target.value)}
                placeholder="content, fact, character…"
              />
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
          {chunks.isLoading ? (
            <PageLoading />
          ) : chunks.error ? (
            <ErrorState
              error={chunks.error}
              retry={() => void chunks.refetch()}
            />
          ) : chunks.data!.items.length ? (
            <div className="table-wrap">
              <table>
                <caption>Memory chunk metadata and bounded previews</caption>
                <thead>
                  <tr>
                    <th>Source</th>
                    <th>Chapter / version</th>
                    <th>Preview</th>
                    <th>Characters</th>
                    <th>Embedding</th>
                    <th>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {chunks.data!.items.map((item) => (
                    <tr key={item.id}>
                      <td>
                        {item.source_type} #{item.chunk_index}
                      </td>
                      <td>
                        {item.chapter_id ?? "—"} /{" "}
                        {item.chapter_version_id ?? "—"}
                      </td>
                      <td className="max-w-xl">{item.content_preview}</td>
                      <td>{item.character_count}</td>
                      <td>
                        {item.embedding_provider} / {item.embedding_model}
                      </td>
                      <td>{formatDate(item.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState
              title="No accepted memory"
              message="Filters and data-layer status constraints excluded every chunk."
            />
          )}
        </Section>
      </div>
    </>
  );
}
