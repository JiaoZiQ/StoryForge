"use client";

import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useEvaluations } from "@/hooks/use-storyforge";
import { storyforgeApi } from "@/lib/api/storyforge";
import {
  ErrorState,
  PageLoading,
  ScoreBadge,
  StatusBadge,
} from "@/components/ui/states";
import { humanize } from "@/lib/formatting";

export function EvaluationPanel({
  projectId,
  chapterNumber,
}: {
  projectId: number;
  chapterNumber: number;
}) {
  const history = useEvaluations(projectId, chapterNumber);
  const [selectedEvaluation, setSelectedEvaluation] = useState(0);
  const selected = selectedEvaluation || history.data?.items[0]?.id || 0;
  const detail = useQuery({
    queryKey: ["evaluation", projectId, chapterNumber, selected],
    queryFn: ({ signal }) =>
      storyforgeApi.getEvaluation(projectId, chapterNumber, selected, signal),
    enabled: selected > 0,
  });
  if (history.isLoading) return <PageLoading label="Loading evaluations…" />;
  if (history.error)
    return (
      <ErrorState error={history.error} retry={() => void history.refetch()} />
    );
  if (!history.data!.items.length)
    return (
      <p className="text-ink-600">No evaluations exist for this chapter.</p>
    );
  return (
    <div className="grid gap-5">
      <label className="label max-w-sm">
        Evaluation version
        <select
          className="field"
          value={selected}
          onChange={(event) =>
            setSelectedEvaluation(Number(event.target.value))
          }
        >
          {history.data!.items.map((item) => (
            <option key={item.id} value={item.id}>
              Evaluation {item.evaluation_version} ·{" "}
              {item.final_score.toFixed(2)}
            </option>
          ))}
        </select>
      </label>
      {detail.isLoading ? (
        <PageLoading />
      ) : detail.error ? (
        <ErrorState error={detail.error} retry={() => void detail.refetch()} />
      ) : detail.data ? (
        <EvaluationDetailView evaluation={detail.data} />
      ) : null}
    </div>
  );
}
export function EvaluationDetailView({
  evaluation,
}: {
  evaluation: Awaited<ReturnType<typeof storyforgeApi.getEvaluation>>;
}) {
  const dimensions = Object.entries(evaluation.raw_scores);
  return (
    <div className="grid gap-5">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
        <Metric label="Final" value={evaluation.final_score} />
        <Metric label="Mechanical" value={evaluation.mechanical_score} />
        <Metric label="Critic" value={evaluation.critic_score} />
        <Metric label="Consistency" value={evaluation.consistency_score} />
        <section className="rounded-lg border border-black/10 bg-white p-4">
          <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
            Decision
          </p>
          <div className="mt-2">
            <StatusBadge
              value={
                evaluation.passed ? "passed" : evaluation.recommended_action
              }
            />
          </div>
        </section>
      </div>
      {evaluation.blocking_reasons.length ? (
        <section className="rounded-lg border border-red-700/20 bg-red-50 p-4">
          <h3 className="font-bold text-red-950">Blocking reasons</h3>
          <ul className="mt-2 list-disc pl-5 text-sm">
            {evaluation.blocking_reasons.map((reason) => (
              <li key={reason}>{humanize(reason)}</li>
            ))}
          </ul>
        </section>
      ) : null}
      <section>
        <h3 className="font-bold">Dimension scores</h3>
        <div className="mt-3 grid gap-3 sm:grid-cols-2">
          {dimensions.map(([name, value]) => (
            <div key={name}>
              <div className="flex justify-between text-sm">
                <span>{humanize(name)}</span>
                <strong>{value.toFixed(2)}</strong>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded bg-black/10">
                <div
                  className="h-full bg-teal"
                  style={{
                    width: `${Math.max(0, Math.min(100, value * 10))}%`,
                  }}
                />
              </div>
            </div>
          ))}
        </div>
      </section>
      <section>
        <h3 className="font-bold">Issues</h3>
        {evaluation.issues.length ? (
          <div className="mt-3 grid gap-3">
            {evaluation.issues.map((issue) => (
              <article
                key={issue.id}
                className={`rounded-lg border p-4 ${["critical", "high"].includes(issue.severity) ? "border-red-700/30 bg-red-50" : "border-black/10 bg-white"}`}
              >
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <strong>
                    {issue.code} · {issue.category}
                  </strong>
                  <StatusBadge value={issue.severity} />
                </div>
                <p className="mt-2">{issue.description}</p>
                {issue.evidence ? (
                  <blockquote className="mt-2 border-l-4 border-black/15 pl-3 text-sm text-ink-600">
                    {issue.evidence}
                  </blockquote>
                ) : null}
                {issue.suggestion ? (
                  <p className="mt-2 text-sm">
                    <strong>Suggestion:</strong> {issue.suggestion}
                  </p>
                ) : null}
              </article>
            ))}
          </div>
        ) : (
          <p className="mt-2 text-ink-600">No issues recorded.</p>
        )}
      </section>
      <details>
        <summary className="font-bold">Evaluation provenance</summary>
        <dl className="mt-3 grid gap-2 text-sm">
          <dt>Provider / model</dt>
          <dd>
            {evaluation.provider} / {evaluation.model}
          </dd>
          <dt>Evaluator versions</dt>
          <dd>{JSON.stringify(evaluation.evaluator_versions)}</dd>
          <dt>Prompt versions</dt>
          <dd>{JSON.stringify(evaluation.prompt_versions)}</dd>
          <dt>Weighted scores</dt>
          <dd>{JSON.stringify(evaluation.weighted_scores)}</dd>
        </dl>
      </details>
    </div>
  );
}
function Metric({ label, value }: { label: string; value: number }) {
  return (
    <section className="rounded-lg border border-black/10 bg-white p-4">
      <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </p>
      <div className="mt-2">
        <ScoreBadge score={value} />
      </div>
    </section>
  );
}
