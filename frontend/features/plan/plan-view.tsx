"use client";

import { useState } from "react";
import { ApiClientError } from "@/lib/api/errors";
import { useGeneratePlan, usePlan, useProject } from "@/hooks/use-storyforge";
import { PageHeader, Section } from "@/components/ui/page";
import {
  ApiErrorAlert,
  ConfirmDialog,
  ErrorState,
  InlineLoading,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";

export function PlanView({ projectId }: { projectId: number }) {
  const project = useProject(projectId);
  const plan = usePlan(projectId);
  const generate = useGeneratePlan(projectId);
  const [confirmReplace, setConfirmReplace] = useState(false);
  if (project.isLoading || plan.isLoading)
    return <PageLoading label="Loading project plan…" />;
  if (project.error)
    return (
      <ErrorState error={project.error} retry={() => void project.refetch()} />
    );
  const missing =
    plan.error instanceof ApiClientError &&
    (plan.error.status === 404 ||
      (plan.error.status === 409 && plan.error.code === "state_conflict"));
  if (plan.error && !missing)
    return <ErrorState error={plan.error} retry={() => void plan.refetch()} />;
  const run = async (replace: boolean) => {
    setConfirmReplace(false);
    await generate.mutateAsync(replace);
  };
  if (missing)
    return (
      <>
        <PageHeader
          eyebrow="Planning"
          title="Generate the story plan"
          description={project.data!.premise}
        />
        <section className="surface rounded-xl p-8 text-center">
          <p className="text-ink-600">
            StoryForge will synchronously generate the overview, characters,
            locations, three chapter outlines, and foreshadowing.
          </p>
          <button
            className="button-primary mt-5"
            type="button"
            disabled={generate.isPending}
            onClick={() => void run(false)}
          >
            {generate.isPending ? "Generating plan…" : "Generate plan"}
          </button>
          {generate.isPending ? (
            <div className="mt-3">
              <InlineLoading label="This request continues only while this page remains connected." />
            </div>
          ) : null}
          {generate.error ? (
            <div className="mt-4">
              <ApiErrorAlert error={generate.error} />
            </div>
          ) : null}
        </section>
      </>
    );
  const data = plan.data!;
  return (
    <>
      <PageHeader
        eyebrow="Planning"
        title="Story plan"
        description={`${data.chapter_plans.length} chapters · ${data.characters.length} characters · ${data.locations.length} locations`}
        actions={
          <button
            className="button-secondary"
            type="button"
            onClick={() => setConfirmReplace(true)}
          >
            Replace plan
          </button>
        }
      />
      {generate.error ? <ApiErrorAlert error={generate.error} /> : null}
      <div className="grid gap-6">
        <Section title="Overview">
          <div className="grid gap-5 md:grid-cols-2">
            <Text label="Themes" value={data.themes.join(", ")} />
            <Text label="Central conflict" value={data.central_conflict} />
            <Text label="World summary" value={data.world_summary} />
            <Text label="Style guide" value={data.style_guide} />
          </div>
        </Section>
        <Section title="Characters">
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {data.characters.map((character) => (
              <article
                className="rounded-lg border border-black/10 bg-white p-4"
                key={character.name}
              >
                <div className="flex items-start justify-between gap-2">
                  <h3 className="font-bold">{character.name}</h3>
                  <span className="text-xs text-ink-600">{character.role}</span>
                </div>
                <p className="mt-2 text-sm text-ink-600">
                  {character.description}
                </p>
                <p className="mt-3 text-sm">
                  <strong>Goals:</strong> {character.goals.join(", ")}
                </p>
                <p className="mt-1 text-sm">
                  <strong>Voice:</strong> {character.speech_style}
                </p>
                <div className="mt-3">
                  <StatusBadge value={character.current_state} />
                </div>
                <details className="mt-3 text-sm">
                  <summary className="font-semibold">
                    Author-side traits
                  </summary>
                  <p className="mt-2">
                    {character.personality_traits.join(", ")}
                  </p>
                </details>
              </article>
            ))}
          </div>
        </Section>
        <Section title="Locations">
          <div className="grid gap-4 md:grid-cols-2">
            {data.locations.map((location) => (
              <article
                className="rounded-lg border border-black/10 bg-white p-4"
                key={location.name}
              >
                <h3 className="font-bold">{location.name}</h3>
                <p className="mt-2 text-sm text-ink-600">
                  {location.description}
                </p>
                {location.rules.length ? (
                  <ul className="mt-3 list-disc pl-5 text-sm">
                    {location.rules.map((rule) => (
                      <li key={rule}>{rule}</li>
                    ))}
                  </ul>
                ) : null}
              </article>
            ))}
          </div>
        </Section>
        <Section title="Chapter outline">
          <div className="grid gap-4">
            {data.chapter_plans.map((chapter) => (
              <article
                className="rounded-lg border border-black/10 bg-white p-4"
                key={chapter.chapter_number}
              >
                <p className="text-xs font-bold uppercase tracking-widest text-copper-dark">
                  Chapter {chapter.chapter_number}
                </p>
                <h3 className="mt-1 text-lg font-bold">{chapter.title}</h3>
                <p className="mt-2 text-ink-600">{chapter.objective}</p>
                <p className="mt-2 text-sm">{chapter.summary}</p>
                <div className="mt-3 grid gap-3 text-sm md:grid-cols-2">
                  <Text
                    label="Key events"
                    value={chapter.key_events.join(" · ")}
                  />
                  <Text
                    label="Characters / locations"
                    value={[
                      ...chapter.participating_characters,
                      ...chapter.locations,
                    ].join(" · ")}
                  />
                  <Text
                    label="Required facts"
                    value={chapter.required_facts.join(" · ") || "None"}
                  />
                  <Text
                    label="Forbidden reveals"
                    value={chapter.forbidden_reveals.join(" · ") || "None"}
                  />
                </div>
              </article>
            ))}
          </div>
        </Section>
        <Section title="Foreshadowing">
          <div className="table-wrap">
            <table>
              <caption>Planned setups and payoffs</caption>
              <thead>
                <tr>
                  <th>Description</th>
                  <th>Setup</th>
                  <th>Payoff</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {data.foreshadowing.map((item) => (
                  <tr key={item.id}>
                    <td>{item.description}</td>
                    <td>Chapter {item.setup_chapter}</td>
                    <td>Chapter {item.expected_payoff_chapter}</td>
                    <td>
                      <StatusBadge value={item.status} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Section>
      </div>
      <ConfirmDialog
        open={confirmReplace}
        title="Replace the existing plan?"
        message="StoryForge will reject replacement if generated chapter content or an active workflow makes this unsafe. Existing work is never silently overwritten."
        confirmLabel="Replace plan"
        onCancel={() => setConfirmReplace(false)}
        onConfirm={() => void run(true)}
      />
    </>
  );
}
function Text({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs font-bold uppercase tracking-widest text-ink-600">
        {label}
      </p>
      <p className="mt-1 leading-relaxed">{value || "—"}</p>
    </div>
  );
}
