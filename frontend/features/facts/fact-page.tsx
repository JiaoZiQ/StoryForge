"use client";

import { useFacts } from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";
import { clipText } from "@/lib/formatting";

export function FactPage({ projectId }: { projectId: number }) {
  const query = useFacts(projectId);
  return (
    <>
      <PageHeader
        eyebrow="Long-term truth"
        title="Accepted facts"
        description="The public API enforces accepted-only facts; candidate, rejected, superseded, current, and future facts are unavailable."
      />
      {query.isLoading ? (
        <PageLoading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data!.items.length === 0 ? (
        <EmptyState
          title="No accepted facts"
          message="Facts become public memory only after a chapter version is accepted."
        />
      ) : (
        <section className="surface rounded-xl p-4">
          <div className="table-wrap">
            <table>
              <caption>Accepted structured facts</caption>
              <thead>
                <tr>
                  <th>Fact</th>
                  <th>Chapter / version</th>
                  <th>Confidence</th>
                  <th>Validity</th>
                  <th>Source quote</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {query.data!.items.map((fact) => (
                  <tr key={fact.id}>
                    <td>
                      <strong>{fact.subject}</strong> {fact.predicate}{" "}
                      {fact.object}
                      <p className="mt-1 text-xs text-ink-600">
                        {fact.fact_type}
                      </p>
                    </td>
                    <td>
                      {fact.chapter_number} / {fact.chapter_version_id}
                    </td>
                    <td>{fact.confidence.toFixed(2)}</td>
                    <td>
                      {fact.valid_from_chapter}–
                      {fact.valid_to_chapter ?? "open"}
                    </td>
                    <td>{clipText(fact.source_quote, 180)}</td>
                    <td>
                      <StatusBadge value={fact.status} />
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
