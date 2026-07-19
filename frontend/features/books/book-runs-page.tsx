"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  ErrorState,
  EmptyState,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";
import { PageHeader, Section } from "@/components/ui/page";
import { useBookRuns, useCreateBookRun } from "@/hooks/use-storyforge";

export function BookRunsPage({ projectId }: { projectId: number }) {
  const router = useRouter();
  const runs = useBookRuns(projectId);
  const create = useCreateBookRun(projectId);
  if (runs.isLoading) return <PageLoading label="Loading whole-book runs…" />;
  if (runs.error || !runs.data)
    return <ErrorState error={runs.error} retry={() => void runs.refetch()} />;
  return (
    <>
      <PageHeader
        eyebrow="Milestone 12"
        title="Book runs"
        description="Generate accepted chapters in dependency order, then freeze and review an immutable whole-book snapshot. No manuscript body is loaded on this page."
        actions={
          <button
            type="button"
            className="button-primary"
            disabled={create.isPending}
            onClick={() =>
              create.mutate(undefined, {
                onSuccess: (value) =>
                  router.push(
                    `/projects/${projectId}/book/${value.book_run_id}`,
                  ),
              })
            }
          >
            {create.isPending ? "Starting…" : "Start sequential book run"}
          </button>
        }
      />
      {create.error ? <ErrorState error={create.error} /> : null}
      {runs.data.items.length === 0 ? (
        <EmptyState
          title="No whole-book run yet"
          message="Complete project planning, then start a run. StoryForge will use asynchronous jobs and accepted chapter versions."
        />
      ) : (
        <Section
          title="Run history"
          description={`${runs.data.total_items} durable run(s)`}
        >
          <div className="table-wrap">
            <table>
              <caption className="sr-only">Whole-book run history</caption>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Status</th>
                  <th>Progress</th>
                  <th>Chapters</th>
                  <th>Global round</th>
                  <th>Cost</th>
                </tr>
              </thead>
              <tbody>
                {runs.data.items.map((run) => (
                  <tr key={run.id}>
                    <td>
                      <Link
                        className="font-bold text-copper-dark underline"
                        href={`/projects/${projectId}/book/${run.id}`}
                      >
                        #{run.id}
                      </Link>
                    </td>
                    <td>
                      <StatusBadge value={run.status} />
                    </td>
                    <td>{run.progress}%</td>
                    <td>
                      {run.accepted_chapters}/{run.total_chapters}
                    </td>
                    <td>
                      {run.current_global_revision_round}/
                      {run.max_global_revision_rounds}
                    </td>
                    <td>{run.spent_cost} USD</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      )}
    </>
  );
}
