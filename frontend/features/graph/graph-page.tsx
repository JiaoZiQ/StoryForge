"use client";

import { useCallback, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { storyforgeApi } from "@/lib/api/storyforge";
import { useGraphEntities, useGraphRelations } from "@/hooks/use-storyforge";
import { validateGraphHops } from "@/features/shared/workflow";
import { PageHeader, Section, StatCard } from "@/components/ui/page";
import {
  EmptyState,
  ErrorState,
  PageLoading,
  StatusBadge,
} from "@/components/ui/states";
import { GraphCanvas } from "./graph-canvas";
import { clipText, humanize } from "@/lib/formatting";

export function GraphPage({ projectId }: { projectId: number }) {
  const [search, setSearch] = useState("");
  const [chapter, setChapter] = useState(2);
  const [hops, setHops] = useState<1 | 2>(1);
  const [entityId, setEntityId] = useState(0);
  const [relationId, setRelationId] = useState(0);
  const entities = useGraphEntities(projectId, search);
  const relations = useGraphRelations(projectId, chapter);
  const neighbors = useQuery({
    queryKey: ["graph-neighbors", projectId, entityId, chapter, hops],
    queryFn: ({ signal }) =>
      storyforgeApi.graphNeighbors(projectId, entityId, chapter, hops, signal),
    enabled: entityId > 0,
  });
  const selectEntity = useCallback((id: number) => {
    setEntityId(id);
    setRelationId(0);
  }, []);
  const selectRelation = useCallback((id: number) => {
    setRelationId(id);
  }, []);
  const graphEntities = neighbors.data?.entities ?? entities.data?.items ?? [];
  const graphRelations =
    neighbors.data?.relations ?? relations.data?.items ?? [];
  const selectedRelation = graphRelations.find(
    (item) => item.id === relationId,
  );
  const selectedEntity = graphEntities.find((item) => item.id === entityId);
  return (
    <>
      <PageHeader
        eyebrow="Knowledge graph"
        title="Story relationships"
        description="Accepted entities and relations only. Traversal is explicitly limited to one or two hops."
      />
      <form
        className="surface mb-5 grid gap-3 rounded-xl p-4 sm:grid-cols-3"
        aria-label="Graph controls"
        onSubmit={(event) => event.preventDefault()}
      >
        <label className="label">
          Entity search
          <input
            className="field"
            value={search}
            onChange={(event) => {
              setSearch(event.target.value);
              setEntityId(0);
            }}
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
          Traversal
          <select
            className="field"
            value={hops}
            onChange={(event) =>
              setHops(validateGraphHops(Number(event.target.value)))
            }
          >
            <option value={1}>1 hop</option>
            <option value={2}>2 hops</option>
          </select>
        </label>
      </form>
      {entities.isLoading || relations.isLoading ? (
        <PageLoading />
      ) : entities.error ? (
        <ErrorState error={entities.error} />
      ) : relations.error ? (
        <ErrorState error={relations.error} />
      ) : graphEntities.length === 0 ? (
        <EmptyState
          title="No graph entities"
          message="Run and accept a chapter workflow, then build its memory index."
        />
      ) : (
        <div className="grid gap-6">
          <div className="grid gap-4 sm:grid-cols-3">
            <StatCard label="Visible entities" value={graphEntities.length} />
            <StatCard label="Visible relations" value={graphRelations.length} />
            <StatCard
              label="Traversal"
              value={`${hops} hop${hops === 1 ? "" : "s"}`}
            />
          </div>
          {neighbors.error ? (
            <ErrorState
              error={neighbors.error}
              retry={() => void neighbors.refetch()}
            />
          ) : null}
          <Section
            title="Interactive graph"
            description="Characters use circles, locations diamonds, and other types rounded rectangles; the list below is an equivalent text view."
          >
            <GraphCanvas
              entities={graphEntities}
              relations={graphRelations}
              onEntity={selectEntity}
              onRelation={selectRelation}
            />
          </Section>
          {selectedEntity || selectedRelation ? (
            <Section title="Selection details">
              {selectedEntity ? (
                <div>
                  <StatusBadge value={selectedEntity.entity_type} />
                  <h3 className="mt-2 text-lg font-bold">
                    {selectedEntity.canonical_name}
                  </h3>
                  <p className="mt-2 text-ink-600">
                    {selectedEntity.description || "No description"}
                  </p>
                </div>
              ) : null}
              {selectedRelation ? (
                <div>
                  <StatusBadge value={selectedRelation.predicate} />
                  <p className="mt-2">
                    <strong>{selectedRelation.subject_name}</strong> →{" "}
                    <strong>{selectedRelation.object_name}</strong>
                  </p>
                  <p className="mt-2 text-ink-600">
                    {clipText(selectedRelation.evidence, 500)}
                  </p>
                </div>
              ) : null}
            </Section>
          ) : null}
          <Section title="Accessible graph list">
            <div className="grid gap-5 lg:grid-cols-2">
              <div>
                <h3 className="font-bold">Entities</h3>
                <ul className="mt-3 grid gap-2">
                  {graphEntities.map((entity) => (
                    <li key={entity.id}>
                      <button
                        className="w-full rounded border border-black/10 bg-white p-3 text-left"
                        type="button"
                        onClick={() => selectEntity(entity.id)}
                      >
                        <strong>{entity.canonical_name}</strong>
                        <span className="ml-2 text-sm text-ink-600">
                          {humanize(entity.entity_type)}
                        </span>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
              <div>
                <h3 className="font-bold">Relations</h3>
                <ul className="mt-3 grid gap-2">
                  {graphRelations.map((relation) => (
                    <li key={relation.id}>
                      <button
                        className="w-full rounded border border-black/10 bg-white p-3 text-left"
                        type="button"
                        onClick={() => selectRelation(relation.id)}
                      >
                        <strong>{relation.subject_name}</strong>{" "}
                        {humanize(relation.predicate)}{" "}
                        <strong>{relation.object_name}</strong>
                      </button>
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          </Section>
        </div>
      )}
    </>
  );
}
