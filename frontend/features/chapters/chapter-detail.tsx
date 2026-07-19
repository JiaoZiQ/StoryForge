"use client";

import Link from "next/link";
import { useState } from "react";
import { useRouter } from "next/navigation";
import {
  useChapter,
  useConflicts,
  useContext,
  useGenerateChapter,
  useStartWorkflow,
  useWorkflows,
} from "@/hooks/use-storyforge";
import { PageHeader } from "@/components/ui/page";
import {
  ApiErrorAlert,
  ErrorState,
  InlineLoading,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { VersionPanel } from "./version-panel";
import { EvaluationPanel } from "@/features/evaluations/evaluation-panel";
import { ConflictTable } from "@/features/conflicts/conflict-table";

const tabs = [
  "overview",
  "content",
  "outline",
  "versions",
  "evaluations",
  "conflicts",
  "context",
  "workflow",
] as const;
type Tab = (typeof tabs)[number];

export function ChapterDetailView({
  projectId,
  chapterNumber,
  initialTab = "overview",
}: {
  projectId: number;
  chapterNumber: number;
  initialTab?: string;
}) {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>(
    tabs.includes(initialTab as Tab) ? (initialTab as Tab) : "overview",
  );
  const chapter = useChapter(projectId, chapterNumber, tab === "content");
  const generate = useGenerateChapter(projectId, chapterNumber);
  const workflow = useStartWorkflow(projectId, chapterNumber);
  if (chapter.isLoading) return <PageLoading label="Loading chapter…" />;
  if (chapter.error)
    return (
      <ErrorState error={chapter.error} retry={() => void chapter.refetch()} />
    );
  const data = chapter.data!;
  const choose = (next: Tab) => {
    setTab(next);
    router.replace(
      `/projects/${projectId}/chapters/${chapterNumber}?tab=${next}`,
      { scroll: false },
    );
  };
  const runWorkflow = async () => {
    const result = await workflow.mutateAsync();
    router.push(`/jobs/${result.job_id}`);
  };
  const generateDraft = async () => {
    const result = await generate.mutateAsync();
    router.push(`/jobs/${result.job_id}`);
  };
  return (
    <>
      <PageHeader
        eyebrow={`Chapter ${chapterNumber}`}
        title={data.title}
        description={data.objective}
        actions={
          <>
            <button
              className="button-secondary"
              type="button"
              disabled={generate.isPending || workflow.isPending}
              onClick={() => void generateDraft()}
            >
              {generate.isPending ? "Generating…" : "Generate draft"}
            </button>
            <button
              className="button-primary"
              type="button"
              disabled={generate.isPending || workflow.isPending}
              onClick={() => void runWorkflow()}
            >
              {workflow.isPending ? "Running workflow…" : "Run full workflow"}
            </button>
          </>
        }
      />
      {generate.isPending || workflow.isPending ? (
        <div className="mb-4">
          <InlineLoading label="Creating a durable background job…" />
        </div>
      ) : null}
      {generate.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={generate.error} />
        </div>
      ) : null}
      {workflow.error ? (
        <div className="mb-4">
          <ApiErrorAlert error={workflow.error} />
        </div>
      ) : null}
      <div className="mb-5 overflow-x-auto">
        <div
          role="tablist"
          aria-label="Chapter detail sections"
          className="flex min-w-max gap-2"
        >
          {tabs.map((item) => (
            <button
              key={item}
              role="tab"
              aria-selected={tab === item}
              type="button"
              className={`rounded-lg px-3 py-2 text-sm font-bold ${tab === item ? "bg-ink-950 text-white" : "border border-black/15 bg-white"}`}
              onClick={() => choose(item)}
            >
              {item[0]!.toUpperCase() + item.slice(1)}
            </button>
          ))}
        </div>
      </div>
      <section className="surface rounded-xl p-5 sm:p-6" role="tabpanel">
        <TabContent
          tab={tab}
          projectId={projectId}
          chapterNumber={chapterNumber}
          data={data}
        />
      </section>
    </>
  );
}

function TabContent({
  tab,
  projectId,
  chapterNumber,
  data,
}: {
  tab: Tab;
  projectId: number;
  chapterNumber: number;
  data: Awaited<
    ReturnType<typeof import("@/lib/api/storyforge").storyforgeApi.getChapter>
  >;
}) {
  if (tab === "overview")
    return (
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Info label="Status">
          <StatusBadge value={data.status} />
        </Info>
        <Info label="Score">
          <ScoreBadge score={data.score} />
        </Info>
        <Info label="Current version">
          {data.current_version?.version ?? "—"}
        </Info>
        <Info label="Accepted / best">
          {data.accepted_version?.version ?? "—"} /{" "}
          {data.best_version?.version ?? "—"}
        </Info>
        <Info label="Versions">{data.version_count}</Info>
        <Info label="Conflicts">{data.conflict_count}</Info>
        <Info label="Workflow">
          <StatusBadge value={data.workflow_status ?? "not_started"} />
        </Info>
        <Info label="Content">
          {data.has_content ? "Available" : "Not generated"}
        </Info>
      </div>
    );
  if (tab === "content")
    return data.content ? (
      <div>
        <div className="mb-4 flex flex-wrap gap-3 text-sm text-ink-600">
          <span>{data.content.length.toLocaleString()} characters</span>
          <span>Current v{data.current_version?.version ?? "—"}</span>
          <span>Accepted v{data.accepted_version?.version ?? "—"}</span>
          <span>Best v{data.best_version?.version ?? "—"}</span>
        </div>
        <article className="prose-text rounded-lg bg-white p-5">
          {data.content}
        </article>
      </div>
    ) : (
      <p className="text-ink-600">No chapter content exists yet.</p>
    );
  if (tab === "outline")
    return (
      <div className="grid gap-4">
        <Info label="Objective">{data.objective}</Info>
        <Info label="Outline">{data.outline}</Info>
        <details>
          <summary className="font-bold">Structured outline metadata</summary>
          <pre className="mt-3 overflow-auto rounded bg-ink-950 p-4 text-xs text-white">
            {JSON.stringify(data.outline_metadata, null, 2)}
          </pre>
        </details>
      </div>
    );
  if (tab === "versions")
    return <VersionPanel projectId={projectId} chapterNumber={chapterNumber} />;
  if (tab === "evaluations")
    return (
      <EvaluationPanel projectId={projectId} chapterNumber={chapterNumber} />
    );
  if (tab === "conflicts")
    return (
      <ChapterConflicts projectId={projectId} chapterNumber={chapterNumber} />
    );
  if (tab === "context")
    return (
      <ChapterContextPanel
        projectId={projectId}
        chapterNumber={chapterNumber}
      />
    );
  return (
    <ChapterWorkflowPanel projectId={projectId} chapterNumber={chapterNumber} />
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
      <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </p>
      <div className="mt-2 leading-relaxed">{children}</div>
    </div>
  );
}
function ChapterConflicts({
  projectId,
  chapterNumber,
}: {
  projectId: number;
  chapterNumber: number;
}) {
  const query = useConflicts(projectId, { chapterNumber });
  return query.isLoading ? (
    <PageLoading />
  ) : query.error ? (
    <ErrorState error={query.error} />
  ) : (
    <ConflictTable projectId={projectId} conflicts={query.data!.items} />
  );
}
function ChapterContextPanel({
  projectId,
  chapterNumber,
}: {
  projectId: number;
  chapterNumber: number;
}) {
  const query = useContext(projectId, chapterNumber);
  if (query.isLoading) return <PageLoading />;
  if (query.error) return <ErrorState error={query.error} />;
  const data = query.data!;
  return (
    <div className="grid gap-5">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Info label="Characters">{data.characters.join(", ") || "None"}</Info>
        <Info label="Locations">{data.locations.join(", ") || "None"}</Info>
        <Info label="Known facts">{data.known_fact_count}</Info>
        <Info label="Hybrid hits">{data.memory_hit_count}</Info>
      </div>
      <Info label="Active foreshadowing">
        {data.active_foreshadowing.join(" · ") || "None"}
      </Info>
      <Info label="Omitted categories">
        {data.truncated_categories.join(", ") || "None"}
      </Info>
      <details>
        <summary className="font-bold">Safe context metadata</summary>
        <pre className="mt-3 overflow-auto rounded bg-ink-950 p-4 text-xs text-white">
          {JSON.stringify(data.metadata, null, 2)}
        </pre>
      </details>
    </div>
  );
}
function ChapterWorkflowPanel({
  projectId,
  chapterNumber,
}: {
  projectId: number;
  chapterNumber: number;
}) {
  const query = useWorkflows(projectId);
  if (query.isLoading) return <PageLoading />;
  if (query.error) return <ErrorState error={query.error} />;
  const runs = query.data!.items.filter(
    (run) => run.chapter_number === chapterNumber,
  );
  return runs.length ? (
    <div className="grid gap-3">
      {runs.map((run) => (
        <Link
          key={run.workflow_run_id}
          className="rounded-lg border border-black/10 bg-white p-4"
          href={`/projects/${projectId}/workflow/${run.workflow_run_id}`}
        >
          <div className="flex items-center justify-between">
            <strong>Run {run.workflow_run_id}</strong>
            <StatusBadge value={run.status} />
          </div>
          <p className="mt-2 text-sm text-ink-600">
            {run.current_node} · revision {run.revision_attempt}/
            {run.max_revision_attempts}
          </p>
        </Link>
      ))}
    </div>
  ) : (
    <p className="text-ink-600">No workflow history for this chapter.</p>
  );
}
