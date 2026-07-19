"use client";

import Link from "next/link";
import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { queryKeys } from "@/lib/query/keys";
import { ErrorState, PageLoading, StatusBadge } from "@/components/ui/states";
import { PageHeader, Section, StatCard } from "@/components/ui/page";

const terminal = new Set(["succeeded", "failed", "cancelled", "dead_lettered"]);
const jobTypes = [
  "generate_plan",
  "generate_chapter",
  "evaluate_chapter",
  "run_chapter_workflow",
  "resume_workflow",
  "reindex_memory",
  "run_retrieval_warmup",
];

export function JobCenter() {
  const [status, setStatus] = useState("");
  const [jobType, setJobType] = useState("");
  const [projectId, setProjectId] = useState("");
  const [chapterNumber, setChapterNumber] = useState("");
  const [createdFrom, setCreatedFrom] = useState("");
  const [createdTo, setCreatedTo] = useState("");
  const filters = {
    status,
    jobType,
    projectId,
    chapterNumber,
    createdFrom,
    createdTo,
  };
  const jobs = useQuery({
    queryKey: queryKeys.jobs(filters),
    queryFn: ({ signal }) =>
      storyforgeApi.listJobs(
        {
          status: status || undefined,
          jobType: jobType || undefined,
          projectId: projectId ? Number(projectId) : undefined,
          chapterNumber: chapterNumber ? Number(chapterNumber) : undefined,
          createdFrom: createdFrom
            ? new Date(createdFrom).toISOString()
            : undefined,
          createdTo: createdTo ? new Date(createdTo).toISOString() : undefined,
        },
        signal,
      ),
    refetchInterval: (query) =>
      query.state.data?.items.some((job) => !terminal.has(job.status))
        ? 3_000
        : false,
  });
  const health = useQuery({
    queryKey: ["queue", "health"],
    queryFn: ({ signal }) => storyforgeApi.queueHealth(signal),
    refetchInterval: 10_000,
  });
  if (jobs.isLoading) return <PageLoading label="Loading asynchronous jobs…" />;
  if (jobs.error)
    return <ErrorState error={jobs.error} retry={() => void jobs.refetch()} />;
  const items = jobs.data?.items ?? [];
  const active = items.filter((job) => !terminal.has(job.status)).length;
  return (
    <>
      <PageHeader
        eyebrow="Operations"
        title="Job Center"
        description="Durable queue state, attempts, progress, and safe worker-facing metadata."
      />
      <div className="mb-6 grid gap-4 sm:grid-cols-3">
        <StatCard label="Visible jobs" value={jobs.data?.total_items ?? 0} />
        <StatCard label="Active" value={active} />
        <StatCard
          label="Dead letter"
          value={items.filter((job) => job.status === "dead_lettered").length}
        />
      </div>
      {health.data &&
      (!health.data.broker_reachable || health.data.workers.length === 0) ? (
        <p
          role="alert"
          className="mb-5 rounded border border-amber-400 bg-amber-50 p-3"
        >
          API is available, but the queue broker or workers are not ready.
        </p>
      ) : null}
      {health.data?.soft_limit_exceeded ? (
        <p
          role="status"
          className="mb-5 rounded border border-amber-400 bg-amber-50 p-3"
        >
          Queue depth exceeds the soft limit ({health.data.pending_jobs}/
          {health.data.pending_soft_limit}).
        </p>
      ) : null}
      <Section
        title="Jobs"
        description="Results never include prompts, API keys, or chapter bodies."
      >
        <div className="mb-4 grid gap-3 md:grid-cols-3">
          <FilterSelect
            label="Status"
            value={status}
            onChange={setStatus}
            options={[
              "queued",
              "running",
              "paused",
              "retry_scheduled",
              "succeeded",
              "failed",
              "dead_lettered",
              "cancelled",
            ]}
          />
          <FilterSelect
            label="Type"
            value={jobType}
            onChange={setJobType}
            options={jobTypes}
          />
          <FilterInput
            label="Project ID"
            value={projectId}
            onChange={setProjectId}
          />
          <FilterInput
            label="Chapter number"
            value={chapterNumber}
            onChange={setChapterNumber}
          />
          <FilterInput
            label="Created from"
            value={createdFrom}
            onChange={setCreatedFrom}
            type="datetime-local"
          />
          <FilterInput
            label="Created to"
            value={createdTo}
            onChange={setCreatedTo}
            type="datetime-local"
          />
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead>
              <tr className="border-b border-black/10">
                <th className="p-2">ID</th>
                <th>Type</th>
                <th>Project / chapter</th>
                <th>Status</th>
                <th>Progress</th>
                <th>Attempt</th>
                <th>Step</th>
              </tr>
            </thead>
            <tbody>
              {items.map((job) => (
                <tr key={job.id} className="border-b border-black/5">
                  <td className="p-2">
                    <Link
                      className="font-bold text-copper-dark underline"
                      href={`/jobs/${job.id}`}
                    >
                      #{job.id}
                    </Link>
                  </td>
                  <td>{job.job_type}</td>
                  <td>
                    {job.project_id ?? "—"} / {job.chapter_number ?? "—"}
                  </td>
                  <td>
                    <StatusBadge value={job.status} />
                  </td>
                  <td>{job.progress}%</td>
                  <td>
                    {job.attempt}/{job.max_attempts}
                  </td>
                  <td>{job.current_step ?? "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}

function FilterSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  options: string[];
}) {
  return (
    <label className="block text-sm font-bold">
      {label}
      <select
        className="mt-1 w-full rounded border border-black/20 bg-white p-2"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">All</option>
        {options.map((option) => (
          <option key={option}>{option}</option>
        ))}
      </select>
    </label>
  );
}

function FilterInput({
  label,
  value,
  onChange,
  type = "text",
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  type?: string;
}) {
  return (
    <label className="block text-sm font-bold">
      {label}
      <input
        className="mt-1 w-full rounded border border-black/20 p-2"
        type={type}
        value={value}
        onChange={(event) => onChange(event.target.value)}
      />
    </label>
  );
}
