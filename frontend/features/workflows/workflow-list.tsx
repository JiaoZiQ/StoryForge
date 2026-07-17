"use client";

import Link from "next/link";
import { useWorkflows } from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function WorkflowList({ projectId }: { projectId: number }) {
  const query = useWorkflows(projectId);
  return (
    <>
      <PageHeader
        eyebrow="Automation"
        title="Workflow runs"
        description="Auditable node progress with bounded polling. This page does not claim real-time push."
      />
      {query.isLoading ? (
        <PageLoading />
      ) : query.error ? (
        <ErrorState error={query.error} retry={() => void query.refetch()} />
      ) : query.data!.items.length === 0 ? (
        <EmptyState
          title="No workflows"
          message="Open a chapter and start a full workflow to generate, evaluate, and revise it."
        />
      ) : (
        <section className="surface rounded-xl p-4">
          <div className="table-wrap">
            <table>
              <caption>Current and historical workflow runs</caption>
              <thead>
                <tr>
                  <th>Run</th>
                  <th>Chapter</th>
                  <th>Status</th>
                  <th>Node</th>
                  <th>Revision</th>
                  <th>Versions</th>
                  <th>Score</th>
                  <th>Started</th>
                </tr>
              </thead>
              <tbody>
                {query.data!.items.map((run) => (
                  <tr key={run.workflow_run_id}>
                    <td>
                      <Link
                        className="font-bold text-copper-dark hover:underline"
                        href={`/projects/${projectId}/workflow/${run.workflow_run_id}`}
                      >
                        #{run.workflow_run_id}
                      </Link>
                    </td>
                    <td>{run.chapter_number}</td>
                    <td>
                      <StatusBadge value={run.status} />
                    </td>
                    <td>{run.current_node}</td>
                    <td>
                      {run.revision_attempt}/{run.max_revision_attempts}
                    </td>
                    <td>
                      best {run.best_version ?? "—"} / accepted{" "}
                      {run.accepted_version ?? "—"}
                    </td>
                    <td>
                      <ScoreBadge score={run.latest_score} />
                    </td>
                    <td>{formatDate(run.started_at)}</td>
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
