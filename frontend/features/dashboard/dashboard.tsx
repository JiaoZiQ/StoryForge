"use client";

import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import { useProjects } from "@/hooks/use-storyforge";
import { PageHeader, StatCard, Section } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function Dashboard() {
  const projects = useProjects({ pageSize: 5 });
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: storyforgeApi.health,
  });
  const ready = useQuery({
    queryKey: queryKeys.readiness,
    queryFn: storyforgeApi.readiness,
    retry: false,
  });
  if (projects.isLoading) return <PageLoading />;
  if (projects.error)
    return (
      <ErrorState
        error={projects.error}
        retry={() => void projects.refetch()}
      />
    );
  const data = projects.data!;
  return (
    <>
      <PageHeader
        eyebrow="Control room"
        title="StoryForge Dashboard"
        description="Plan stories, inspect revision workflows, and trace accepted memory without exposing model credentials."
        actions={
          <Link className="button-primary" href="/projects/new">
            Create project
          </Link>
        }
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Projects"
          value={data.meta.total_items}
          detail="Visible StoryForge projects"
        />
        <StatCard
          label="API"
          value={
            <StatusBadge
              value={
                health.data?.status ?? (health.isError ? "failed" : "checking")
              }
            />
          }
          detail={health.data?.version}
        />
        <StatCard
          label="Readiness"
          value={
            <StatusBadge
              value={
                ready.data?.status ?? (ready.isError ? "not_ready" : "checking")
              }
            />
          }
          detail={ready.data?.migration_revision ?? "Migration status"}
        />
        <StatCard
          label="Provider"
          value={ready.data?.provider ?? "—"}
          detail="Keys are never shown in the UI"
        />
      </div>
      <div className="mt-6">
        <Section title="Recent projects">
          {data.items.length === 0 ? (
            <EmptyState
              title="No projects yet"
              message="Create a project to generate a three-chapter plan and run an offline Mock workflow."
              action={
                <Link className="button-primary" href="/projects/new">
                  Create the first project
                </Link>
              }
            />
          ) : (
            <div className="grid gap-3">
              {data.items.map((project) => (
                <Link
                  className="rounded-lg border border-black/10 bg-white p-4 transition hover:border-copper"
                  href={`/projects/${project.id}`}
                  key={project.id}
                >
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <strong>{project.title}</strong>
                    <StatusBadge value={project.status} />
                  </div>
                  <p className="mt-2 text-sm text-ink-600">
                    {project.genre} · {project.language} · updated{" "}
                    {formatDate(project.updated_at)}
                  </p>
                </Link>
              ))}
            </div>
          )}
        </Section>
      </div>
    </>
  );
}
