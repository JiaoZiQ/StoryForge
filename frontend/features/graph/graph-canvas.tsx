"use client";

import cytoscape, { type Core, type ElementDefinition } from "cytoscape";
import { useEffect, useRef } from "react";
import type {
  GraphEntityResponse,
  GraphRelationResponse,
} from "@/lib/api/types";

export function GraphCanvas({
  entities,
  relations,
  onEntity,
  onRelation,
}: {
  entities: GraphEntityResponse[];
  relations: GraphRelationResponse[];
  onEntity: (id: number) => void;
  onRelation: (id: number) => void;
}) {
  const container = useRef<HTMLDivElement>(null);
  const graph = useRef<Core | null>(null);
  useEffect(() => {
    if (!container.current) return;
    const elements: ElementDefinition[] = [
      ...entities.map((entity) => ({
        data: {
          id: `n${entity.id}`,
          entityId: entity.id,
          label: entity.canonical_name,
          type: entity.entity_type,
        },
      })),
      ...relations.map((relation) => ({
        data: {
          id: `e${relation.id}`,
          relationId: relation.id,
          source: `n${relation.subject_entity_id}`,
          target: `n${relation.object_entity_id}`,
          label: relation.predicate,
        },
      })),
    ];
    const instance = cytoscape({
      container: container.current,
      elements,
      layout: { name: "cose", animate: false, fit: true, padding: 32 },
      style: [
        {
          selector: "node",
          style: {
            "background-color": "#267a77",
            "border-color": "#155553",
            "border-width": 2,
            color: "#121619",
            label: "data(label)",
            shape: "round-rectangle",
            "font-size": "12px",
            "text-valign": "bottom",
            "text-margin-y": 8,
          },
        },
        {
          selector: "node[type = 'character']",
          style: { shape: "ellipse", "background-color": "#b75d37" },
        },
        {
          selector: "node[type = 'location']",
          style: { shape: "diamond", "background-color": "#d5a535" },
        },
        {
          selector: "edge",
          style: {
            width: 2,
            "line-color": "#708089",
            "target-arrow-color": "#708089",
            "target-arrow-shape": "triangle",
            "curve-style": "bezier",
            label: "data(label)",
            "font-size": "9px",
            "text-background-color": "#f5f1e8",
            "text-background-opacity": 0.9,
            "text-background-padding": "2px",
          },
        },
      ],
    });
    instance.on("tap", "node", (event) =>
      onEntity(Number(event.target.data("entityId"))),
    );
    instance.on("tap", "edge", (event) =>
      onRelation(Number(event.target.data("relationId"))),
    );
    graph.current = instance;
    return () => {
      instance.destroy();
      graph.current = null;
    };
  }, [entities, relations, onEntity, onRelation]);
  return (
    <div>
      <div
        ref={container}
        className="h-[34rem] w-full rounded-lg border border-black/15 bg-white"
        role="img"
        aria-label={`Story graph with ${entities.length} entities and ${relations.length} relations`}
      />
      <button
        className="button-secondary mt-3"
        type="button"
        onClick={() => graph.current?.fit(undefined, 32)}
      >
        Reset graph view
      </button>
    </div>
  );
}
