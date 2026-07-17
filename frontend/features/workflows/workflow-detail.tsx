"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import { workflowActions } from "@/features/shared/workflow";
import { useWorkflow, useWorkflowEvents } from "@/hooks/use-storyforge";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  ApiErrorAlert,
  ConfirmDialog,
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate, humanize } from "@/lib/formatting";
import { useState } from "react";

export function WorkflowDetail({
  workflowRunId,
}: {
  projectId: number;
  workflowRunId: number;
}) {
  const queryClient = useQueryClient();
  const workflow = useWorkflow(workflowRunId);
  const events = useWorkflowEvents(workflowRunId, workflow.data?.status);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const resume = useMutation({
    mutationFn: () => storyforgeApi.resumeWorkflow(workflowRunId),
    onSuccess: async () => {
      await queryClient.invalidateQueries({
        queryKey: queryKeys.workflow(workflowRunId),
      });
    },
  });
  const cancel = useMutation({
    mutationFn: () => storyforgeApi.cancelWorkflow(workflowRunId),
    onSuccess: async () => {
      setConfirmCancel(false);
      await queryClient.invalidateQueries({
        queryKey: queryKeys.workflow(workflowRunId),
      });
    },
  });
  if (workflow.isLoading) return <PageLoading label="Loading workflow…" />;
  if (workflow.error)
    return (
      <ErrorState
        error={workflow.error}
        retry={() => void workflow.refetch()}
      />
    );
  const data = workflow.data!;
  const actions = workflowActions(data.status);
  return (
    <>
      <PageHeader
        eyebrow={`Workflow ${data.workflow_run_id}`}
        title={`Chapter ${data.chapter_number} workflow`}
        description={`Current node: ${humanize(data.current_node)}. Running and paused workflows poll every three seconds while the page is visible.`}
        actions={
          <>
            {actions.canResume ? (
              <button
                className="button-primary"
                type="button"
                disabled={resume.isPending}
                onClick={() => void resume.mutate()}
              >
                Resume
              </button>
            ) : null}
            {actions.canCancel ? (
              <button
                className="button-secondary"
                type="button"
                disabled={cancel.isPending}
                onClick={() => setConfirmCancel(true)}
              >
                Cancel
              </button>
            ) : null}
          </>
        }
      />
      {resume.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={resume.error} />
        </div>
      ) : null}
      {cancel.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={cancel.error} />
        </div>
      ) : null}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Status" value={<StatusBadge value={data.status} />} />
        <StatCard
          label="Revision"
          value={`${data.revision_attempt}/${data.max_revision_attempts}`}
        />
        <StatCard label="Best version" value={data.best_version ?? "—"} />
        <StatCard
          label="Accepted version"
          value={data.accepted_version ?? "—"}
        />
        <StatCard
          label="Latest score"
          value={<ScoreBadge score={data.latest_score} />}
        />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-[2fr_1fr]">
        <Section
          title="Node timeline"
          description="Events contain identifiers and timings, never raw checkpoint data or prose."
        >
          {events.isLoading ? (
            <PageLoading />
          ) : events.error ? (
            <ErrorState
              error={events.error}
              retry={() => void events.refetch()}
            />
          ) : (
            <ol className="relative grid gap-3 border-l-2 border-black/10 pl-5">
              {events.data!.items.map((event) => (
                <li
                  key={event.id}
                  className="rounded-lg border border-black/10 bg-white p-4"
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong>{humanize(event.node)}</strong>
                    <StatusBadge value={event.event_type} />
                  </div>
                  <p className="mt-2 text-sm text-ink-600">
                    Attempt {event.attempt} · {event.duration_ms} ms ·{" "}
                    {formatDate(event.created_at)}
                  </p>
                  {event.error_code ? (
                    <p className="mt-2 text-sm text-red-800">
                      {humanize(event.error_code)}
                    </p>
                  ) : null}
                </li>
              ))}
            </ol>
          )}
        </Section>
        <Section title="Decision record">
          <dl className="grid gap-4 text-sm">
            <Info label="Original">v{data.original_version ?? "—"}</Info>
            <Info label="Current">v{data.current_version ?? "—"}</Info>
            <Info label="Best">v{data.best_version ?? "—"}</Info>
            <Info label="Accepted">v{data.accepted_version ?? "—"}</Info>
            <Info label="Started">{formatDate(data.started_at)}</Info>
            <Info label="Finished">{formatDate(data.finished_at)}</Info>
            <Info label="Blocking reasons">
              {data.blocking_reasons.map(humanize).join(", ") || "None"}
            </Info>
            {data.error_code ? (
              <Info label="Error">
                {humanize(data.error_code)} — {data.error_message}
              </Info>
            ) : null}
          </dl>
        </Section>
      </div>
      <ConfirmDialog
        open={confirmCancel}
        title="Cancel this workflow?"
        message="Cancellation is cooperative and takes effect at the next node boundary. Existing accepted content is preserved."
        confirmLabel="Cancel workflow"
        onCancel={() => setConfirmCancel(false)}
        onConfirm={() => void cancel.mutate()}
      />
    </>
  );
}
function Info({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <dt className="font-bold text-ink-600">{label}</dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}
