"use client";

import { useQuery } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import { ErrorState, PageLoading, StatusBadge } from "@/components/ui/states";

export function SystemPage() {
  const health = useQuery({
    queryKey: queryKeys.health,
    queryFn: storyforgeApi.health,
  });
  const ready = useQuery({
    queryKey: queryKeys.readiness,
    queryFn: storyforgeApi.readiness,
    retry: false,
  });
  if (health.isLoading) return <PageLoading />;
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="System status"
        description="Minimal, safe runtime information. Database URLs, credentials, provider keys, and base URLs are deliberately absent."
      />
      {health.error ? (
        <ErrorState error={health.error} />
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatCard
            label="API health"
            value={<StatusBadge value={health.data!.status} />}
          />
          <StatCard label="Backend version" value={health.data!.version} />
          <StatCard label="Environment" value={health.data!.environment} />
          <StatCard
            label="Readiness"
            value={
              <StatusBadge
                value={
                  ready.data?.status ?? (ready.error ? "not_ready" : "checking")
                }
              />
            }
          />
        </div>
      )}
      <div className="mt-6">
        <Section title="Runtime boundary">
          <dl className="grid gap-4 sm:grid-cols-2">
            <Info label="Database">
              {ready.data?.database ?? "Unavailable"}
            </Info>
            <Info label="Migration revision">
              {ready.data?.migration_revision ?? "Unavailable"}
            </Info>
            <Info label="LLM provider mode">
              {ready.data?.provider ?? "Unavailable"}
            </Info>
            <Info label="Embedding mode">
              Configured server-side; never exposed by readiness
            </Info>
          </dl>
        </Section>
      </div>
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
      <dt className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </dt>
      <dd className="mt-1">{children}</dd>
    </div>
  );
}
