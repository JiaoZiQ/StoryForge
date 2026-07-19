"use client";

import { useEffect, useMemo, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import {
  ErrorState,
  EmptyState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  useBookAnalysis,
  useBookEvaluation,
  useBookRun,
  useBookRunEvents,
  useBookSnapshots,
  useBookTimeline,
  useBookRevisionPlan,
  useControlBookRun,
} from "@/hooks/use-storyforge";
import { queryKeys } from "@/lib/query/keys";
import type { BookRunResponse, BookSnapshotResponse } from "@/lib/api/types";

const terminal = new Set([
  "completed",
  "completed_needs_review",
  "cancelled",
  "failed",
]);
const tabs = [
  "Progress",
  "Snapshot",
  "Timeline",
  "Character arcs",
  "Relationships",
  "Foreshadowing",
  "Pacing",
  "Transitions",
  "Global evaluation",
  "Revision plan",
] as const;
type Tab = (typeof tabs)[number];

export function BookRunWorkspace({
  projectId,
  runId,
}: {
  projectId: number;
  runId: number;
}) {
  const client = useQueryClient();
  const [tab, setTab] = useState<Tab>("Progress");
  const [realtime, setRealtime] = useState("polling fallback");
  const run = useBookRun(runId);
  const events = useBookRunEvents(runId, run.data?.status);
  const snapshots = useBookSnapshots(projectId);
  const control = useControlBookRun(projectId, runId);
  const snapshotId =
    run.data?.book_snapshot_id ?? run.data?.best_snapshot_id ?? 0;
  const evaluation = useBookEvaluation(snapshotId);
  const timeline = useBookTimeline(snapshotId);
  const arcs = useBookAnalysis(snapshotId, "character-arcs");
  const relationships = useBookAnalysis(snapshotId, "relationships");
  const foreshadowing = useBookAnalysis(snapshotId, "foreshadowing");
  const pacing = useBookAnalysis(snapshotId, "pacing");
  const transitions = useBookAnalysis(snapshotId, "transitions");
  const revision = useBookRevisionPlan(snapshotId);
  const snapshot = useMemo(
    () => snapshots.data?.items.find((item) => item.id === snapshotId),
    [snapshotId, snapshots.data?.items],
  );

  useEffect(() => {
    if (
      terminal.has(run.data?.status ?? "") ||
      typeof EventSource === "undefined"
    )
      return;
    const source = new EventSource(
      `/backend/api/v1/book-runs/${runId}/events/stream`,
    );
    const refresh = () => {
      void client.invalidateQueries({ queryKey: queryKeys.bookRun(runId) });
      void client.invalidateQueries({
        queryKey: queryKeys.bookRunEvents(runId),
      });
    };
    source.onopen = () => setRealtime("SSE live");
    source.onmessage = refresh;
    for (const name of [
      "job_progress",
      "workflow_node_started",
      "workflow_node_completed",
      "job_succeeded",
      "job_failed",
      "job_paused",
    ])
      source.addEventListener(name, refresh);
    source.onerror = () => setRealtime("polling fallback");
    return () => source.close();
  }, [client, run.data?.status, runId]);

  if (run.isLoading) return <PageLoading label="Loading full-book progress…" />;
  if (run.error || !run.data)
    return <ErrorState error={run.error} retry={() => void run.refetch()} />;
  const value = run.data;
  return (
    <>
      <PageHeader
        eyebrow="Whole-book workflow"
        title={`Book run #${value.id}`}
        description={`Current node: ${value.current_node}. SSE stops at terminal state; bounded polling remains the fallback.`}
        actions={
          <div className="flex flex-wrap gap-2">
            {[
              "planning_validation",
              "generating",
              "global_review",
              "global_revision",
            ].includes(value.status) ? (
              <button
                className="button-secondary"
                type="button"
                onClick={() => control.mutate("pause")}
              >
                Pause
              </button>
            ) : null}
            {["paused", "budget_blocked"].includes(value.status) ? (
              <button
                className="button-primary"
                type="button"
                onClick={() => control.mutate("resume")}
              >
                Resume
              </button>
            ) : null}
            {!terminal.has(value.status) ? (
              <button
                className="button-secondary"
                type="button"
                onClick={() => control.mutate("cancel")}
              >
                Cancel
              </button>
            ) : null}
          </div>
        }
      />
      {control.error ? <ErrorState error={control.error} /> : null}
      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        <StatCard label="Status" value={<StatusBadge value={value.status} />} />
        <StatCard
          label="Progress"
          value={`${value.progress}%`}
          detail={`${value.completed_chapters}/${value.total_chapters} completed`}
        />
        <StatCard
          label="Accepted"
          value={value.accepted_chapters}
          detail={`${value.needs_review_chapters} need review`}
        />
        <StatCard
          label="Global round"
          value={`${value.current_global_revision_round}/${value.max_global_revision_rounds}`}
        />
        <StatCard
          label="Cost"
          value={value.spent_cost}
          detail={`${value.remaining_cost} USD remaining`}
        />
      </div>
      <div
        className="mb-6 overflow-x-auto"
        role="tablist"
        aria-label="Whole-book analysis views"
      >
        <div className="flex min-w-max gap-2">
          {tabs.map((name) => (
            <button
              key={name}
              type="button"
              role="tab"
              aria-selected={tab === name}
              className={tab === name ? "button-primary" : "button-secondary"}
              onClick={() => setTab(name)}
            >
              {name}
            </button>
          ))}
        </div>
      </div>
      <div role="tabpanel" aria-label={tab}>
        {tab === "Progress" ? (
          <Progress
            run={value}
            events={events.data?.items ?? []}
            realtime={terminal.has(value.status) ? "stopped" : realtime}
          />
        ) : null}
        {tab === "Snapshot" ? <SnapshotView snapshot={snapshot} /> : null}
        {tab === "Timeline" ? (
          <DataView
            title="Timeline"
            score={null}
            items={timeline.data?.items}
            loading={timeline.isLoading}
            error={timeline.error}
            empty="No accepted timeline events."
          />
        ) : null}
        {tab === "Character arcs" ? (
          <AnalysisView title="Character arcs" query={arcs} />
        ) : null}
        {tab === "Relationships" ? (
          <AnalysisView title="Relationship history" query={relationships} />
        ) : null}
        {tab === "Foreshadowing" ? (
          <AnalysisView title="Foreshadowing" query={foreshadowing} />
        ) : null}
        {tab === "Pacing" ? (
          <AnalysisView title="Pacing" query={pacing} bars />
        ) : null}
        {tab === "Transitions" ? (
          <AnalysisView title="Chapter transitions" query={transitions} />
        ) : null}
        {tab === "Global evaluation" ? (
          <EvaluationView
            value={evaluation.data}
            loading={evaluation.isLoading}
            error={evaluation.error}
          />
        ) : null}
        {tab === "Revision plan" ? (
          <RevisionView
            value={revision.data}
            loading={revision.isLoading}
            error={revision.error}
          />
        ) : null}
      </div>
    </>
  );
}

function Progress({
  run,
  events,
  realtime,
}: {
  run: BookRunResponse;
  events: Array<{
    id: number;
    message: string;
    status: string;
    step?: string | null;
    progress: number;
  }>;
  realtime: string;
}) {
  if (!run) return null;
  const periodicChecks = run.periodic_checks ?? [];
  return (
    <div className="grid gap-6 xl:grid-cols-2">
      <Section
        title="Chapter dependency progress"
        description={`Transport: ${realtime}`}
      >
        <ol className="space-y-3">
          {Object.entries(run.chapter_status).map(([chapter, status]) => (
            <li
              key={chapter}
              className="flex items-center justify-between rounded border border-black/10 p-3"
            >
              <span className="font-bold">Chapter {chapter}</span>
              <StatusBadge value={status} />
            </li>
          ))}
        </ol>
      </Section>
      <Section
        title="Durable event timeline"
        description="Messages are content-free and ordered for SSE replay."
      >
        <ol className="space-y-3">
          {events.map((event) => (
            <li key={event.id} className="border-l-2 border-copper/40 pl-4">
              <strong>{event.message}</strong>
              <p className="text-sm text-ink-600">
                {event.step ?? "event"} · {event.progress}% · {event.status}
              </p>
            </li>
          ))}
        </ol>
      </Section>
      <Section
        title="Periodic global checks"
        description="Accepted-only checks run at configured chapter boundaries."
      >
        {periodicChecks.length ? (
          <ol className="space-y-3">
            {periodicChecks.map((check, index) => (
              <li key={index} className="rounded border border-black/10 p-3">
                Through chapter {String(check.through_chapter ?? "?")}: timeline{" "}
                {String(check.timeline_score ?? "?")}/10, character arc{" "}
                {String(check.character_arc_score ?? "?")}/10, pacing{" "}
                {String(check.pacing_score ?? "?")}/10. Critical conflicts:{" "}
                {String(check.critical_conflicts ?? 0)}.
              </li>
            ))}
          </ol>
        ) : (
          <p>No periodic checkpoint has been reached yet.</p>
        )}
      </Section>
    </div>
  );
}

function SnapshotView({
  snapshot,
}: {
  snapshot: BookSnapshotResponse | undefined;
}) {
  if (!snapshot)
    return (
      <EmptyState
        title="No snapshot yet"
        message="A frozen chapter-version map appears after all chapters reach a reviewable state."
      />
    );
  return (
    <Section
      title={`Snapshot #${snapshot.snapshot_number}`}
      description="Immutable version references; no chapter body is copied or loaded."
    >
      <div className="mb-4 grid gap-3 sm:grid-cols-3">
        <StatCard
          label="Status"
          value={<StatusBadge value={snapshot.status} />}
        />
        <StatCard label="Words" value={snapshot.total_words} />
        <StatCard
          label="Accepted chapters"
          value={`${snapshot.accepted_chapter_count}/${snapshot.chapter_count}`}
        />
      </div>
      <ol className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {Object.entries(snapshot.chapter_version_map).map(
          ([chapter, version]) => (
            <li key={chapter} className="rounded border border-black/10 p-3">
              Chapter {chapter} → version ID {version}
            </li>
          ),
        )}
      </ol>
    </Section>
  );
}

type AnalysisQuery = ReturnType<typeof useBookAnalysis>;
function AnalysisView({
  title,
  query,
  bars = false,
}: {
  title: string;
  query: AnalysisQuery;
  bars?: boolean;
}) {
  return (
    <DataView
      title={title}
      score={query.data?.score ?? null}
      items={query.data?.items}
      summary={query.data?.summary}
      loading={query.isLoading}
      error={query.error}
      empty={`No ${title.toLowerCase()} data for this snapshot.`}
      bars={bars}
    />
  );
}

function DataView({
  title,
  score,
  items,
  summary,
  loading,
  error,
  empty,
  bars = false,
}: {
  title: string;
  score: number | null;
  items?: Record<string, unknown>[];
  summary?: Record<string, unknown>;
  loading: boolean;
  error: unknown;
  empty: string;
  bars?: boolean;
}) {
  if (loading) return <PageLoading label={`Loading ${title.toLowerCase()}…`} />;
  if (error) return <ErrorState error={error} />;
  if (!items?.length)
    return <EmptyState title={`No ${title.toLowerCase()}`} message={empty} />;
  return (
    <Section
      title={title}
      description="Every visual value is also available as text."
    >
      {score !== null ? (
        <p className="mb-4">
          Score: <ScoreBadge score={score} />
        </p>
      ) : null}
      {summary ? <KeyValues value={summary} /> : null}
      <ol className="mt-5 space-y-3">
        {items.map((item, index) => {
          const numeric =
            typeof item.chapter_score === "number"
              ? item.chapter_score
              : typeof item.score === "number"
                ? item.score
                : null;
          return (
            <li
              key={String(item.id ?? item.event_key ?? index)}
              className="rounded border border-black/10 p-4"
            >
              {bars && numeric !== null ? (
                <div className="mb-2 h-2 rounded bg-black/10">
                  <div
                    className="h-2 rounded bg-teal"
                    style={{
                      width: `${Math.max(0, Math.min(100, numeric * 10))}%`,
                    }}
                  />
                </div>
              ) : null}
              <KeyValues value={item} />
            </li>
          );
        })}
      </ol>
    </Section>
  );
}

function EvaluationView({
  value,
  loading,
  error,
}: {
  value: ReturnType<typeof useBookEvaluation>["data"];
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PageLoading label="Loading global evaluation…" />;
  if (error || !value) return <ErrorState error={error} />;
  return (
    <Section
      title="Global evaluation"
      description="Acceptance uses score plus critical blockers, ending, character-arc, and foreshadowing thresholds."
    >
      <div className="mb-5 flex flex-wrap items-center gap-4">
        <ScoreBadge score={value.final_score} />
        <StatusBadge
          value={value.passed ? "passed" : value.recommended_action}
        />
      </div>
      <KeyValues value={value.dimension_scores} />
      <h3 className="mt-5 font-bold">Blocking reasons</h3>
      {value.blocking_reasons.length ? (
        <ul className="mt-2 list-disc pl-6">
          {value.blocking_reasons.map((reason) => (
            <li key={reason}>{reason}</li>
          ))}
        </ul>
      ) : (
        <p className="mt-2 text-ink-600">None.</p>
      )}
      <p className="mt-4">
        Priority chapters: {value.priority_chapters.join(", ") || "none"}
      </p>
    </Section>
  );
}

function RevisionView({
  value,
  loading,
  error,
}: {
  value: ReturnType<typeof useBookRevisionPlan>["data"];
  loading: boolean;
  error: unknown;
}) {
  if (loading) return <PageLoading label="Loading targeted revision plan…" />;
  if (error || !value)
    return (
      <EmptyState
        title="No revision plan"
        message="A plan exists only when global evaluation selects bounded targeted rework."
      />
    );
  return (
    <Section
      title={`Revision plan · round ${value.revision_round}`}
      description={`${value.estimated_calls} call(s), ${value.estimated_tokens} tokens, ${value.estimated_cost} estimated cost`}
    >
      <p>Dependency order: {value.dependency_order.join(" → ")}</p>
      <ul className="mt-3 list-disc pl-6">
        {value.global_objectives.map((objective) => (
          <li key={objective}>{objective}</li>
        ))}
      </ul>
      <ol className="mt-5 space-y-3">
        {value.tasks.map((task, index) => (
          <li key={index} className="rounded border border-black/10 p-4">
            <KeyValues value={task} />
          </li>
        ))}
      </ol>
    </Section>
  );
}

function KeyValues({ value }: { value: Record<string, unknown> }) {
  return (
    <dl className="grid gap-x-5 gap-y-2 text-sm sm:grid-cols-2">
      {Object.entries(value).map(([key, item]) => (
        <div key={key} className="min-w-0">
          <dt className="font-bold capitalize">{key.replaceAll("_", " ")}</dt>
          <dd className="break-words text-ink-600">
            {typeof item === "object"
              ? JSON.stringify(item)
              : String(item ?? "—")}
          </dd>
        </div>
      ))}
    </dl>
  );
}
