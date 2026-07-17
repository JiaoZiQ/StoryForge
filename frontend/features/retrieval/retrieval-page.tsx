"use client";

import { useState } from "react";
import { useRetrieval } from "@/hooks/use-storyforge";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  ApiErrorAlert,
  EmptyState,
  InlineLoading,
  StatusBadge,
} from "@/components/ui/states";
import { clipText } from "@/lib/formatting";

const routes = ["keyword", "vector", "fact", "graph"] as const;

export function RetrievalPage({ projectId }: { projectId: number }) {
  const mutation = useRetrieval(projectId);
  const [query, setQuery] = useState("Mara brass key");
  const [chapter, setChapter] = useState(2);
  const [characters, setCharacters] = useState("Mara");
  const [locations, setLocations] = useState("");
  const [sourceTypes, setSourceTypes] = useState("");
  const [included, setIncluded] = useState<string[]>([...routes]);
  const [topK, setTopK] = useState(20);
  const [budget, setBudget] = useState(16000);
  const [debug, setDebug] = useState(false);
  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    mutation.mutate({
      query,
      current_chapter: chapter,
      character_names: split(characters),
      location_names: split(locations),
      source_types: split(sourceTypes),
      include_sources: included as (typeof routes)[number][],
      top_k: topK,
      max_context_chars: budget,
      debug: false,
    });
  };
  const copy = async () => {
    if (!mutation.data) return;
    await navigator.clipboard.writeText(
      JSON.stringify(
        {
          query: mutation.data.query,
          candidates: mutation.data.total_candidates,
          hits: mutation.data.hits.length,
          degraded: mutation.data.degraded,
          sources: mutation.data.hits.map((hit) => hit.sources),
        },
        null,
        2,
      ),
    );
  };
  return (
    <>
      <PageHeader
        eyebrow="RAG debugger"
        title="Hybrid retrieval"
        description="Inspect Keyword, Vector, Fact, and Graph recall without exposing vectors or unrestricted content."
      />
      <form
        className="surface grid gap-4 rounded-xl p-5 sm:grid-cols-2 xl:grid-cols-4"
        onSubmit={submit}
      >
        <label className="label sm:col-span-2 xl:col-span-4">
          Query
          <input
            className="field"
            required
            maxLength={2000}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
        </label>
        <label className="label">
          Current chapter
          <input
            className="field"
            type="number"
            min="1"
            value={chapter}
            onChange={(event) => setChapter(Number(event.target.value))}
          />
        </label>
        <label className="label">
          Top K
          <input
            className="field"
            type="number"
            min="1"
            max="100"
            value={topK}
            onChange={(event) => setTopK(Number(event.target.value))}
          />
        </label>
        <label className="label">
          Context characters
          <input
            className="field"
            type="number"
            min="100"
            max="100000"
            value={budget}
            onChange={(event) => setBudget(Number(event.target.value))}
          />
        </label>
        <label className="label">
          Characters
          <input
            className="field"
            value={characters}
            onChange={(event) => setCharacters(event.target.value)}
            placeholder="comma separated"
          />
        </label>
        <label className="label">
          Locations
          <input
            className="field"
            value={locations}
            onChange={(event) => setLocations(event.target.value)}
            placeholder="comma separated"
          />
        </label>
        <label className="label">
          Source types
          <input
            className="field"
            value={sourceTypes}
            onChange={(event) => setSourceTypes(event.target.value)}
            placeholder="content, fact…"
          />
        </label>
        <fieldset className="sm:col-span-2">
          <legend className="text-sm font-bold text-ink-800">
            Recall routes
          </legend>
          <div className="mt-2 flex flex-wrap gap-4">
            {routes.map((route) => (
              <label key={route} className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={included.includes(route)}
                  onChange={(event) =>
                    setIncluded((values) =>
                      event.target.checked
                        ? [...values, route]
                        : values.filter((value) => value !== route),
                    )
                  }
                />
                {route}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="flex items-center gap-3 sm:col-span-2 xl:col-span-4">
          <button
            className="button-primary"
            type="submit"
            disabled={mutation.isPending || !included.length}
          >
            {mutation.isPending ? "Searching…" : "Run retrieval"}
          </button>
          {mutation.isPending ? <InlineLoading /> : null}
        </div>
      </form>
      {mutation.error ? (
        <div className="mt-5">
          <ApiErrorAlert error={mutation.error} />
        </div>
      ) : null}
      {mutation.data ? (
        <div className="mt-6 grid gap-6">
          {mutation.data.degraded ? (
            <section
              role="alert"
              className="rounded-lg border border-amber-700/30 bg-amber-50 p-4 text-amber-950"
            >
              <strong>Degraded retrieval:</strong>{" "}
              {mutation.data.degraded_reasons.join(", ")}
            </section>
          ) : null}
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
            <StatCard
              label="Keyword"
              value={mutation.data.keyword_candidates}
            />
            <StatCard label="Vector" value={mutation.data.vector_candidates} />
            <StatCard label="Fact" value={mutation.data.fact_candidates} />
            <StatCard label="Graph" value={mutation.data.graph_candidates} />
            <StatCard
              label="Deduplicated"
              value={`${mutation.data.deduplicated_count}/${mutation.data.total_candidates}`}
            />
          </div>
          <Section
            title="Final hits"
            description={`${mutation.data.hits.length} hits · ${mutation.data.estimated_chars} estimated characters · ${mutation.data.omitted_count} omitted`}
          >
            <div className="mb-4 flex gap-2">
              <button
                className="button-secondary"
                type="button"
                onClick={() => void copy()}
              >
                Copy retrieval summary
              </button>
              <button
                className="button-secondary"
                type="button"
                aria-expanded={debug}
                onClick={() => setDebug((value) => !value)}
              >
                Toggle JSON debug
              </button>
            </div>
            {mutation.data.hits.length ? (
              <div className="grid gap-4">
                {mutation.data.hits.map((hit) => (
                  <article
                    className="rounded-lg border border-black/10 bg-white p-4"
                    key={`${hit.source_type}-${hit.id}`}
                  >
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <div className="flex flex-wrap gap-2">
                        {hit.sources.map((source) => (
                          <StatusBadge key={source} value={source} />
                        ))}
                      </div>
                      <strong className="font-mono">
                        {hit.score.toFixed(4)}
                      </strong>
                    </div>
                    <p className="mt-3">{clipText(hit.content, 500)}</p>
                    <p className="mt-3 text-sm text-ink-600">
                      Chapter {hit.chapter_number ?? "project"} · version{" "}
                      {hit.version_id ?? "—"}
                    </p>
                    {hit.entity_names.length ? (
                      <p className="mt-1 text-sm">
                        <strong>Entities:</strong> {hit.entity_names.join(", ")}
                      </p>
                    ) : null}
                    {hit.relation_path.length ? (
                      <p className="mt-1 text-sm">
                        <strong>Path:</strong> {hit.relation_path.join(" → ")}
                      </p>
                    ) : null}
                    <p className="mt-2 text-sm text-ink-600">
                      {hit.explanation}
                    </p>
                  </article>
                ))}
              </div>
            ) : (
              <EmptyState
                title="No retrieval hits"
                message="The query and accepted past-only filters produced no safe result."
              />
            )}
            {debug ? (
              <pre className="mt-4 max-h-[32rem] overflow-auto rounded bg-ink-950 p-4 text-xs text-white">
                {JSON.stringify(mutation.data, null, 2)}
              </pre>
            ) : null}
          </Section>
        </div>
      ) : null}
    </>
  );
}
function split(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}
