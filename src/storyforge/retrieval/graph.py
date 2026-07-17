"""Bounded one- or two-hop relational graph expansion."""

from storyforge.database import SessionFactory
from storyforge.graph import GraphEntityRepository, GraphRelationRepository
from storyforge.models import GraphEntity
from storyforge.retrieval.models import HybridRetrievalRequest, RetrievalHit, RetrievalSource


class GraphRetriever:
    def __init__(
        self,
        session_factory: SessionFactory,
        *,
        max_hops: int = 2,
        max_nodes: int = 50,
        max_edges: int = 100,
    ) -> None:
        if max_hops not in {1, 2}:
            raise ValueError("Graph max_hops must be one or two")
        self._session_factory = session_factory
        self.max_hops = max_hops
        self.max_nodes = max_nodes
        self.max_edges = max_edges

    def retrieve(self, request: HybridRetrievalRequest) -> list[RetrievalHit]:
        if request.source_types and "graph_relation" not in request.source_types:
            return []
        seeds = list(dict.fromkeys((*request.character_names, *request.location_names)))
        with self._session_factory() as session:
            entity_repository = GraphEntityRepository(session)
            relation_repository = GraphRelationRepository(session)
            seed_entities = entity_repository.find_visible(request.project_id, seeds)
            known: dict[int, GraphEntity] = {item.id: item for item in seed_entities}
            frontier = set(known)
            visited_edges: set[int] = set()
            hits: list[RetrievalHit] = []
            for hop in range(1, self.max_hops + 1):
                relations = relation_repository.visible_for_entities(
                    request.project_id,
                    sorted(frontier),
                    current_chapter=request.current_chapter,
                    limit=self.max_edges - len(visited_edges),
                )
                next_frontier: set[int] = set()
                for relation in relations:
                    if relation.id in visited_edges:
                        continue
                    visited_edges.add(relation.id)
                    for entity_id in (relation.subject_entity_id, relation.object_entity_id):
                        if entity_id not in known and len(known) < self.max_nodes:
                            entity = session.get(GraphEntity, entity_id)
                            if entity is not None:
                                known[entity_id] = entity
                                next_frontier.add(entity_id)
                    subject = known.get(relation.subject_entity_id)
                    object_ = known.get(relation.object_entity_id)
                    if subject is None or object_ is None:
                        continue
                    path = [
                        subject.canonical_name,
                        relation.predicate.value,
                        object_.canonical_name,
                    ]
                    hits.append(
                        RetrievalHit(
                            id=relation.id,
                            source=RetrievalSource.GRAPH,
                            matched_sources=[RetrievalSource.GRAPH],
                            source_type="graph_relation",
                            content=" ".join(path),
                            score=max(0.0, min(1.0, relation.confidence * (1 - 0.1 * (hop - 1)))),
                            raw_score=relation.confidence,
                            project_id=relation.project_id,
                            chapter_number=relation.valid_from_chapter,
                            version_id=relation.source_version_id,
                            entity_names=[subject.canonical_name, object_.canonical_name],
                            relation_path=path,
                            metadata={"status": relation.status.value, "hop": hop},
                            explanation=f"graph {hop}-hop path: {' → '.join(path)}",
                        )
                    )
                frontier = next_frontier
                if not frontier or len(visited_edges) >= self.max_edges:
                    break
        return sorted(hits, key=lambda item: (-item.score, item.id))[: request.top_k]
