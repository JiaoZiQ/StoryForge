"use client";

import { useMemo, useState } from "react";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import { ErrorState, PageLoading, StatusBadge } from "@/components/ui/states";
import { useUsage, useUsageCalls } from "@/hooks/use-storyforge";
import { formatDate } from "@/lib/formatting";

export function UsagePage({ projectId }: { projectId: number }) {
  const summary = useUsage(projectId);
  const calls = useUsageCalls(projectId);
  const [task, setTask] = useState("all");
  const [model, setModel] = useState("all");
  const [range, setRange] = useState("all");
  const loadedItems = calls.data?.items;
  const items = useMemo(() => loadedItems ?? [], [loadedItems]);
  const tasks = [...new Set(items.map((item) => item.task_type))].sort();
  const models = [...new Set(items.map((item) => item.model))].sort();
  const filtered = useMemo(() => {
    const newest = Math.max(
      0,
      ...items.map((item) => new Date(item.created_at).getTime()),
    );
    const days = range === "all" ? null : Number(range);
    return items.filter(
      (item) =>
        (task === "all" || item.task_type === task) &&
        (model === "all" || item.model === model) &&
        (days == null ||
          newest - new Date(item.created_at).getTime() <= days * 86_400_000),
    );
  }, [items, model, range, task]);
  const breakdowns = useMemo(
    () => ({
      tasks: aggregate(filtered, (item) => item.task_type),
      models: aggregate(filtered, (item) => item.model),
      workflows: aggregate(filtered, (item) =>
        item.workflow_run_id == null
          ? "No workflow"
          : `Workflow ${item.workflow_run_id}`,
      ),
      days: aggregate(filtered, (item) => item.created_at.slice(0, 10)),
    }),
    [filtered],
  );
  if (summary.isLoading || calls.isLoading) return <PageLoading />;
  if (summary.error) return <ErrorState error={summary.error} />;
  if (calls.error) return <ErrorState error={calls.error} />;
  const data = summary.data!;
  const success = data.calls
    ? `${((data.succeeded / data.calls) * 100).toFixed(1)}%`
    : "—";
  return (
    <>
      <PageHeader
        eyebrow={`Project ${projectId}`}
        title="Usage & cost"
        description="Content-free provider attempts, provider-reported or explicitly estimated tokens, and immutable pricing snapshots."
      />
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatCard
          label="Calls"
          value={data.calls}
          detail={`${success} succeeded`}
        />
        <StatCard
          label="Tokens"
          value={data.total_tokens}
          detail={`${data.input_tokens} input / ${data.output_tokens} output`}
        />
        <StatCard
          label="Estimated cost"
          value={
            data.estimated_cost == null
              ? "Unknown"
              : `${data.currency} ${data.estimated_cost}`
          }
          detail="Estimate, not a provider bill"
        />
        <StatCard
          label="Billed cost"
          value={
            data.billed_cost == null
              ? "Unknown"
              : `${data.currency} ${data.billed_cost}`
          }
          detail={`${data.fallback_count} fallback(s)`}
        />
      </div>
      <div className="mt-6">
        <Section
          title="Filters"
          description="Filters apply to the most recent 100 content-free attempts shown below."
        >
          <div className="grid gap-4 md:grid-cols-3">
            <Filter label="Time range" value={range} onChange={setRange}>
              <option value="all">All loaded calls</option>
              <option value="1">Last 24 hours</option>
              <option value="7">Last 7 days</option>
              <option value="30">Last 30 days</option>
            </Filter>
            <Filter label="Task" value={task} onChange={setTask}>
              <option value="all">All tasks</option>
              {tasks.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Filter>
            <Filter label="Model" value={model} onChange={setModel}>
              <option value="all">All models</option>
              {models.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </Filter>
          </div>
        </Section>
      </div>
      <div className="mt-6 grid gap-6 xl:grid-cols-2">
        <Breakdown title="By task" rows={breakdowns.tasks} />
        <Breakdown title="By model" rows={breakdowns.models} />
        <Breakdown title="By workflow" rows={breakdowns.workflows} />
        <Breakdown title="Daily trend" rows={breakdowns.days} />
      </div>
      <div className="mt-6">
        <Section
          title="Provider attempts"
          description="No prompt, chapter body, API key, base URL, or embedding array is included."
        >
          <div className="table-wrap">
            <table>
              <caption>Most recent provider call audit records</caption>
              <thead>
                <tr>
                  <th>Task</th>
                  <th>Provider / model</th>
                  <th>Status</th>
                  <th>Tokens / source</th>
                  <th>Estimated / billed</th>
                  <th>Latency</th>
                  <th>Created</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((item) => (
                  <tr key={item.id}>
                    <td>{item.task_type}</td>
                    <td>
                      {item.provider}
                      <br />
                      <code>{item.model}</code>
                    </td>
                    <td>
                      <StatusBadge value={item.status} />
                      {item.fallback_index ? (
                        <small className="ml-2">
                          fallback {item.fallback_index}
                        </small>
                      ) : null}
                    </td>
                    <td>
                      {item.total_tokens}
                      <br />
                      <small>{item.usage_source}</small>
                    </td>
                    <td>
                      {item.estimated_cost == null
                        ? "Unknown"
                        : `${item.currency} ${item.estimated_cost}`}
                      <br />
                      <small>
                        billed:{" "}
                        {item.billed_cost == null
                          ? "unknown"
                          : item.billed_cost}
                      </small>
                    </td>
                    <td>{item.latency_ms} ms</td>
                    <td>{formatDate(item.created_at)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
    </>
  );
}

type Call = NonNullable<
  ReturnType<typeof useUsageCalls>["data"]
>["items"][number];

function aggregate(items: Call[], key: (item: Call) => string) {
  const rows = new Map<
    string,
    { calls: number; tokens: number; estimated: number; unknown: boolean }
  >();
  for (const item of items) {
    const label = key(item);
    const row = rows.get(label) ?? {
      calls: 0,
      tokens: 0,
      estimated: 0,
      unknown: false,
    };
    row.calls += 1;
    row.tokens += item.total_tokens;
    row.unknown ||= item.status === "succeeded" && item.estimated_cost == null;
    row.estimated += Number(item.estimated_cost ?? 0);
    rows.set(label, row);
  }
  return [...rows.entries()]
    .map(([label, value]) => ({ label, ...value }))
    .sort((left, right) => left.label.localeCompare(right.label));
}

function Filter({
  label,
  value,
  onChange,
  children,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  children: React.ReactNode;
}) {
  return (
    <label className="label">
      {label}
      <select
        className="field"
        value={value}
        onChange={(event) => onChange(event.target.value)}
      >
        {children}
      </select>
    </label>
  );
}

function Breakdown({
  title,
  rows,
}: {
  title: string;
  rows: ReturnType<typeof aggregate>;
}) {
  return (
    <Section
      title={title}
      description="Text-table equivalent of the usage chart."
    >
      <div className="table-wrap">
        <table>
          <caption>{title} usage breakdown</caption>
          <thead>
            <tr>
              <th>Group</th>
              <th>Calls</th>
              <th>Tokens</th>
              <th>Estimated cost</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr key={row.label}>
                <td>{row.label}</td>
                <td>{row.calls}</td>
                <td>{row.tokens}</td>
                <td>{row.unknown ? "Unknown" : row.estimated.toFixed(8)}</td>
              </tr>
            ))}
            {!rows.length ? (
              <tr>
                <td colSpan={4}>No calls match these filters.</td>
              </tr>
            ) : null}
          </tbody>
        </table>
      </div>
    </Section>
  );
}
