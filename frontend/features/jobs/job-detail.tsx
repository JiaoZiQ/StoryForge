"use client";

import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import { ErrorState, PageLoading, StatusBadge } from "@/components/ui/states";
import { PageHeader, Section, StatCard } from "@/components/ui/page";

const terminal = new Set(["succeeded", "failed", "cancelled", "dead_lettered"]);

export function JobDetail({ jobId }: { jobId: number }) {
  const client = useQueryClient();
  const [realtimeState, setRealtimeState] = useState("polling");
  const terminalInvalidated = useRef(false);
  const job = useQuery({
    queryKey: queryKeys.job(jobId),
    queryFn: ({ signal }) => storyforgeApi.getJob(jobId, signal),
    refetchInterval: (query) =>
      terminal.has(query.state.data?.status ?? "") ? false : 5_000,
  });
  const events = useQuery({
    queryKey: queryKeys.jobEvents(jobId),
    queryFn: ({ signal }) => storyforgeApi.listJobEvents(jobId, signal),
    refetchInterval: terminal.has(job.data?.status ?? "") ? false : 5_000,
  });
  useEffect(() => {
    const value = job.data;
    if (!value || !terminal.has(value.status) || terminalInvalidated.current)
      return;
    terminalInvalidated.current = true;
    void client.invalidateQueries({ queryKey: ["jobs"] });
    if (value.project_id !== null) {
      void client.invalidateQueries({
        queryKey: queryKeys.project(value.project_id),
      });
      void client.invalidateQueries({
        queryKey: queryKeys.usage(value.project_id),
      });
      void client.invalidateQueries({
        queryKey: ["project", value.project_id, "chapters"],
      });
      if (value.chapter_number !== null) {
        void client.invalidateQueries({
          queryKey: [
            "project",
            value.project_id,
            "chapter",
            value.chapter_number,
          ],
        });
      }
    }
  }, [client, job.data]);
  useEffect(() => {
    if (terminal.has(job.data?.status ?? "")) {
      return;
    }
    if (typeof EventSource === "undefined") {
      return;
    }
    const source = new EventSource(
      `/backend/api/v1/jobs/${jobId}/events/stream`,
    );
    source.onopen = () => setRealtimeState("realtime");
    const refresh = () => {
      void client.invalidateQueries({ queryKey: queryKeys.job(jobId) });
      void client.invalidateQueries({ queryKey: queryKeys.jobEvents(jobId) });
    };
    source.onmessage = refresh;
    for (const name of [
      "job_progress",
      "progress_updated",
      "workflow_node_completed",
      "job_succeeded",
      "job_failed",
      "job_cancelled",
      "job_dead_lettered",
    ])
      source.addEventListener(name, refresh);
    source.onerror = () => setRealtimeState("polling");
    return () => source.close();
  }, [client, job.data?.status, jobId]);
  const control = useMutation({
    mutationFn: (action: "cancel" | "pause" | "resume" | "retry" | "discard") =>
      storyforgeApi.controlJob(jobId, action),
    onSuccess: async () => {
      await Promise.all([
        client.invalidateQueries({ queryKey: queryKeys.job(jobId) }),
        client.invalidateQueries({ queryKey: queryKeys.jobEvents(jobId) }),
      ]);
    },
  });
  if (job.isLoading) return <PageLoading label="Loading job…" />;
  if (job.error || !job.data)
    return <ErrorState error={job.error} retry={() => void job.refetch()} />;
  const value = job.data;
  return (
    <>
      <PageHeader
        eyebrow="Asynchronous job"
        title={`Job #${value.id}`}
        description={value.job_type}
        actions={
          <div className="flex gap-2">
            {["queued", "leased", "running"].includes(value.status) ? (
              <button
                className="button-secondary"
                onClick={() => control.mutate("pause")}
              >
                Pause
              </button>
            ) : null}
            {value.status === "paused" ? (
              <button
                className="button-secondary"
                onClick={() => control.mutate("resume")}
              >
                Resume
              </button>
            ) : null}
            {["queued", "leased", "running", "pause_requested"].includes(
              value.status,
            ) ? (
              <button
                className="button-secondary"
                onClick={() => control.mutate("cancel")}
              >
                Cancel
              </button>
            ) : null}
            {value.status === "dead_lettered" ? (
              <>
                <button
                  className="button-secondary"
                  onClick={() => control.mutate("retry")}
                >
                  Retry
                </button>
                <button
                  className="button-secondary"
                  onClick={() => control.mutate("discard")}
                >
                  Discard
                </button>
              </>
            ) : null}
          </div>
        }
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-4">
        <StatCard label="Status" value={<StatusBadge value={value.status} />} />
        <StatCard label="Progress" value={`${value.progress}%`} />
        <StatCard
          label="Attempt"
          value={`${value.attempt}/${value.max_attempts}`}
        />
        <StatCard label="Step" value={value.current_step ?? "—"} />
      </div>
      <Section title="Execution metadata">
        <dl className="grid gap-3 text-sm md:grid-cols-2">
          <Meta
            label="Realtime"
            value={terminal.has(value.status) ? "stopped" : realtimeState}
          />
          <Meta label="Correlation ID" value={value.correlation_id} />
          <Meta
            label="Project / chapter"
            value={`${value.project_id ?? "—"} / ${value.chapter_number ?? "—"}`}
          />
          <Meta label="Worker" value={value.worker_id ?? "unassigned"} />
          <Meta label="Created" value={value.created_at} />
          <Meta label="Finished" value={value.finished_at ?? "—"} />
        </dl>
        {Object.keys(value.result).length > 0 ? (
          <pre className="mt-4 overflow-auto rounded bg-black/5 p-3 text-xs">
            {JSON.stringify(value.result, null, 2)}
          </pre>
        ) : null}
      </Section>
      {value.error_message ? (
        <Section title="Safe error">
          <p className="text-red-900">{value.error_message}</p>
          <code className="text-xs">{value.error_code}</code>
        </Section>
      ) : null}
      <Section
        title="Timeline"
        description="SSE reconnects using browser Last-Event-ID semantics; bounded polling remains active while disconnected."
      >
        {events.error ? (
          <ErrorState
            error={events.error}
            retry={() => void events.refetch()}
          />
        ) : (
          <ol className="space-y-3">
            {events.data?.items.map((event) => (
              <li key={event.id} className="border-l-2 border-copper/40 pl-4">
                <div className="flex flex-wrap gap-2">
                  <strong>{event.message}</strong>
                  <StatusBadge value={event.status} />
                </div>
                <p className="text-sm text-ink-600">
                  {event.step ?? event.event_type} · {event.progress}% · attempt{" "}
                  {event.attempt}
                </p>
              </li>
            ))}
          </ol>
        )}
      </Section>
    </>
  );
}

function Meta({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <dt className="font-bold">{label}</dt>
      <dd className="break-all">{value}</dd>
    </div>
  );
}
