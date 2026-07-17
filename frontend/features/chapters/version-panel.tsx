"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useVersions } from "@/hooks/use-storyforge";
import { storyforgeApi } from "@/lib/api/storyforge";
import {
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { formatDate } from "@/lib/formatting";

export function VersionPanel({
  projectId,
  chapterNumber,
}: {
  projectId: number;
  chapterNumber: number;
}) {
  const versions = useVersions(projectId, chapterNumber);
  const [selectedOldId, setSelectedOldId] = useState(0);
  const [selectedNewId, setSelectedNewId] = useState(0);
  const items = versions.data?.items ?? [];
  const oldId = selectedOldId || items.at(-1)?.id || 0;
  const newId = selectedNewId || items[0]?.id || 0;
  const diff = useQuery({
    queryKey: ["version-diff", projectId, chapterNumber, oldId, newId],
    queryFn: ({ signal }) =>
      storyforgeApi.diffVersions(
        projectId,
        chapterNumber,
        newId,
        oldId,
        signal,
      ),
    enabled: oldId > 0 && newId > 0 && oldId !== newId,
  });
  if (versions.isLoading)
    return <PageLoading label="Loading version history…" />;
  if (versions.error)
    return (
      <ErrorState
        error={versions.error}
        retry={() => void versions.refetch()}
      />
    );
  return (
    <div className="grid gap-6">
      <div className="table-wrap">
        <table>
          <caption>Immutable chapter versions</caption>
          <thead>
            <tr>
              <th>Version</th>
              <th>Status</th>
              <th>Source</th>
              <th>Parent</th>
              <th>Score</th>
              <th>Words</th>
              <th>Model</th>
              <th>Created</th>
            </tr>
          </thead>
          <tbody>
            {versions.data!.items.map((version) => (
              <tr key={version.id}>
                <td>v{version.version}</td>
                <td>
                  <StatusBadge value={version.status} />
                </td>
                <td>{version.source}</td>
                <td>{version.parent_version_id ?? "—"}</td>
                <td>
                  <ScoreBadge score={version.score} />
                </td>
                <td>{version.word_count}</td>
                <td>
                  {version.provider} / {version.model}
                </td>
                <td>{formatDate(version.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {versions.data!.items.length >= 2 ? (
        <section className="rounded-lg border border-black/10 bg-white p-4">
          <h3 className="font-bold">Compare versions</h3>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="label">
              Old version
              <select
                className="field"
                value={oldId}
                onChange={(event) =>
                  setSelectedOldId(Number(event.target.value))
                }
              >
                {versions.data!.items.map((version) => (
                  <option key={version.id} value={version.id}>
                    v{version.version} · {version.status}
                  </option>
                ))}
              </select>
            </label>
            <label className="label">
              New version
              <select
                className="field"
                value={newId}
                onChange={(event) =>
                  setSelectedNewId(Number(event.target.value))
                }
              >
                {versions.data!.items.map((version) => (
                  <option key={version.id} value={version.id}>
                    v{version.version} · {version.status}
                  </option>
                ))}
              </select>
            </label>
          </div>
          {oldId === newId ? (
            <p className="mt-4 text-sm text-ink-600">
              Choose two different versions.
            </p>
          ) : diff.isLoading ? (
            <PageLoading label="Computing server-side diff…" />
          ) : diff.error ? (
            <ErrorState error={diff.error} retry={() => void diff.refetch()} />
          ) : diff.data ? (
            <DiffView diff={diff.data} />
          ) : null}
        </section>
      ) : (
        <p className="text-ink-600">
          A second immutable version is required before a comparison can be
          shown.
        </p>
      )}
    </div>
  );
}

function DiffView({
  diff,
}: {
  diff: Awaited<ReturnType<typeof storyforgeApi.diffVersions>>;
}) {
  const lines = diff.unified_diff?.split("\n") ?? [];
  return (
    <div className="mt-5">
      <div className="flex flex-wrap gap-4 text-sm">
        <span>
          <strong>{diff.additions}</strong> additions
        </span>
        <span>
          <strong>{diff.deletions}</strong> deletions
        </span>
        <span>
          <strong>{diff.changed_line_count}</strong> changed lines
        </span>
        <span>
          <strong>{diff.word_count_delta}</strong> word delta
        </span>
      </div>
      {diff.changes_made.length ? (
        <ul className="mt-3 list-disc pl-5 text-sm">
          {diff.changes_made.map((change) => (
            <li key={change}>{change}</li>
          ))}
        </ul>
      ) : null}
      {diff.truncated ? (
        <p role="note" className="mt-3 rounded bg-amber-50 p-3 text-amber-900">
          The server truncated this large diff.
        </p>
      ) : null}
      <pre
        aria-label="Unified version diff"
        className="mt-4 max-h-[35rem] overflow-auto rounded bg-ink-950 p-4 font-mono text-xs text-white"
      >
        {lines.map((line, index) => (
          <span
            key={`${index}-${line.slice(0, 12)}`}
            className={`block px-2 ${line.startsWith("+") && !line.startsWith("+++") ? "diff-add text-ink-950" : line.startsWith("-") && !line.startsWith("---") ? "diff-del text-ink-950" : ""}`}
          >
            <span className="sr-only">
              {line.startsWith("+")
                ? "Added: "
                : line.startsWith("-")
                  ? "Removed: "
                  : "Context: "}
            </span>
            {line || " "}
          </span>
        ))}
      </pre>
    </div>
  );
}
