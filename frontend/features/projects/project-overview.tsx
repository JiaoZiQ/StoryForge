"use client";

import Link from "next/link";
import {
  useChapters,
  useConflicts,
  useFacts,
  useMemoryStatus,
  useProject,
  useWorkflows,
} from "@/hooks/use-storyforge";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function ProjectOverview({ projectId }: { projectId: number }) {
  const project = useProject(projectId);
  const chapters = useChapters(projectId);
  const workflows = useWorkflows(projectId);
  const conflicts = useConflicts(projectId, { status: "open" });
  const facts = useFacts(projectId);
  const memory = useMemoryStatus(projectId);
  if (project.isLoading) return <PageLoading />;
  if (project.error)
    return (
      <ErrorState error={project.error} retry={() => void project.refetch()} />
    );
  const data = project.data!;
  const accepted =
    chapters.data?.items.filter((chapter) => chapter.accepted_version_id)
      .length ?? 0;
  const review =
    chapters.data?.items.filter(
      (chapter) => chapter.status === "needs_human_review",
    ).length ?? 0;
  return (
    <>
      <PageHeader
        eyebrow={`Project ${data.id}`}
        title={data.title}
        description={data.premise}
        actions={
          <>
            <Link
              className="button-secondary"
              href={`/projects/${projectId}/plan`}
            >
              View plan
            </Link>
            <Link
              className="button-primary"
              href={`/projects/${projectId}/chapters`}
            >
              Open chapters
            </Link>
          </>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Status"
          value={<StatusBadge value={data.status} />}
          detail={`${data.genre} · ${data.language}`}
        />
        <StatCard
          label="Chapters"
          value={`${accepted}/${data.target_chapters}`}
          detail={`${review} need review`}
        />
        <StatCard
          label="Open conflicts"
          value={conflicts.data?.meta.total_items ?? "—"}
          detail="Accepted timeline only"
        />
        <StatCard
          label="Accepted facts"
          value={facts.data?.meta.total_items ?? "—"}
          detail={`${memory.data?.items.reduce((total, item) => total + item.chunk_count, 0) ?? 0} memory chunks`}
        />
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Section title="Story direction">
          <dl className="grid gap-4">
            <Info label="Logline" value={data.logline} />
            <Info label="Themes" value={data.themes.join(", ")} />
            <Info label="World" value={data.world_summary} />
            <Info label="Central conflict" value={data.central_conflict} />
            <Info label="Style guide" value={data.style_guide} />
          </dl>
        </Section>
        <Section title="Recent workflows">
          {workflows.data?.items.length ? (
            <div className="grid gap-3">
              {workflows.data.items.slice(0, 5).map((run) => (
                <Link
                  key={run.workflow_run_id}
                  href={`/projects/${projectId}/workflow/${run.workflow_run_id}`}
                  className="rounded-lg border border-black/10 bg-white p-3"
                >
                  <div className="flex items-center justify-between">
                    <strong>Chapter {run.chapter_number}</strong>
                    <StatusBadge value={run.status} />
                  </div>
                  <div className="mt-2 flex justify-between text-sm text-ink-600">
                    <span>{run.current_node}</span>
                    <ScoreBadge score={run.latest_score} />
                  </div>
                  <p className="mt-1 text-xs text-ink-600">
                    {formatDate(run.updated_at)}
                  </p>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-ink-600">No workflow has run yet.</p>
          )}
        </Section>
      </div>
    </>
  );
}
function Info({
  label,
  value,
}: {
  label: string;
  value: string | null | undefined;
}) {
  return (
    <div>
      <dt className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </dt>
      <dd className="mt-1 leading-relaxed">{value || "Not generated yet"}</dd>
    </div>
  );
}
