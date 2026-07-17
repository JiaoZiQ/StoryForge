"""Memory, graph, and hybrid retrieval use cases shared by API and CLI."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from storyforge.application.common import page_response
from storyforge.application.factory import DomainServiceFactory
from storyforge.database import SessionFactory
from storyforge.enums import ChapterVersionStatus, GraphEntityType, GraphPredicate, MemoryStatus
from storyforge.exceptions import DomainValidationError, EntityNotFoundError
from storyforge.graph import GraphEntityRepository, GraphRelationRepository
from storyforge.memory import MemoryChunkRepository, MemoryIndexRecordRepository
from storyforge.models import Chapter, ChapterVersion, GraphEntity, GraphRelation, MemoryChunk
from storyforge.repositories import ProjectRepository
from storyforge.retrieval import HybridRetrievalRequest, RetrievalSource
from storyforge.schemas.api import (
    GraphEntityResponse,
    GraphNeighborsResponse,
    GraphRelationResponse,
    MemoryDetail,
    MemoryIndexStatusResponse,
    MemoryReindexItem,
    MemoryReindexRequest,
    MemoryReindexResponse,
    MemorySummary,
    PageResponse,
    RetrievalHitResponse,
    RetrievalSearchRequest,
    RetrievalSearchResponse,
)
from storyforge.settings import Settings


class MemoryApplicationService:
    """Orchestrate bounded memory inspection, indexing, and retrieval."""

    def __init__(
        self,
        session_factory: SessionFactory,
        factory: DomainServiceFactory,
        settings: Settings,
    ) -> None:
        self._session_factory = session_factory
        self._factory = factory
        self._settings = settings

    def search(self, project_id: int, request: RetrievalSearchRequest) -> RetrievalSearchResponse:
        self._require_project(project_id)
        if request.top_k > self._settings.retrieval_max_top_k:
            raise DomainValidationError("top_k exceeds the configured retrieval maximum")
        if request.debug and not self._settings.retrieval_debug:
            raise DomainValidationError("Retrieval debug output is disabled")
        result = self._factory.hybrid_retriever().retrieve(
            HybridRetrievalRequest(
                project_id=project_id,
                query=request.query,
                current_chapter=request.current_chapter,
                character_names=request.character_names,
                location_names=request.location_names,
                source_types=request.source_types,
                top_k=request.top_k,
                max_context_chars=request.max_context_chars,
                include_sources=(
                    [RetrievalSource(item) for item in request.include_sources]
                    if request.include_sources is not None
                    else None
                ),
            )
        )
        return RetrievalSearchResponse(
            query=result.query,
            hits=[
                RetrievalHitResponse(
                    id=item.id,
                    source_type=item.source_type,
                    content=item.content,
                    score=item.score,
                    sources=[source.value for source in item.matched_sources],
                    chapter_number=item.chapter_number,
                    version_id=item.version_id,
                    entity_names=item.entity_names,
                    relation_path=item.relation_path,
                    explanation=item.explanation,
                )
                for item in result.hits
            ],
            total_candidates=result.total_candidates,
            keyword_candidates=result.keyword_candidates,
            vector_candidates=result.vector_candidates,
            fact_candidates=result.fact_candidates,
            graph_candidates=result.graph_candidates,
            deduplicated_count=result.deduplicated_count,
            omitted_count=result.omitted_count,
            estimated_chars=result.estimated_chars,
            retrieval_version=result.retrieval_version,
            filters_applied=result.filters_applied,
            degraded=result.degraded,
            degraded_reasons=result.degraded_reasons,
        )

    def list_memory(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        source_type: str | None = None,
        chapter_number: int | None = None,
    ) -> PageResponse[MemorySummary]:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            result = MemoryChunkRepository(session).page_visible(
                project_id,
                page=page,
                page_size=page_size,
                source_type=source_type,
                chapter_number=chapter_number,
            )
            items = [self._memory_summary(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_memory(
        self, project_id: int, memory_id: int, *, include_content: bool = False
    ) -> MemoryDetail:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            item = MemoryChunkRepository(session).get_visible(project_id, memory_id)
            if item is None:
                raise EntityNotFoundError(f"Memory chunk {memory_id} was not found")
            return MemoryDetail(
                **self._memory_summary(item).model_dump(),
                content=item.content if include_content else None,
                metadata=dict(item.details),
            )

    def reindex(self, project_id: int, request: MemoryReindexRequest) -> MemoryReindexResponse:
        if request.force and self._settings.environment == "production":
            raise DomainValidationError("Forced reindex is disabled in production")
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            statement = (
                select(ChapterVersion)
                .join(Chapter, ChapterVersion.chapter_id == Chapter.id)
                .where(
                    Chapter.project_id == project_id,
                    ChapterVersion.status == ChapterVersionStatus.ACCEPTED,
                )
                .order_by(Chapter.chapter_number, ChapterVersion.version)
            )
            if request.chapter_version_id is not None:
                statement = statement.where(ChapterVersion.id == request.chapter_version_id)
            versions = list(session.scalars(statement))
        if request.chapter_version_id is not None and not versions:
            raise EntityNotFoundError("Accepted chapter version was not found for this project")
        indexer = self._factory.memory_index_service()
        results = [
            indexer.index_accepted_chapter_version(item.id, force=request.force)
            for item in versions
        ]
        return MemoryReindexResponse(
            project_id=project_id,
            results=[
                MemoryReindexItem(
                    chapter_version_id=item.chapter_version_id,
                    status=item.status,
                    chunk_count=item.chunk_count,
                    graph_entity_count=item.graph_entity_count,
                    graph_relation_count=item.graph_relation_count,
                    degraded=item.degraded,
                )
                for item in results
            ],
        )

    def list_status(
        self, project_id: int, *, page: int, page_size: int
    ) -> PageResponse[MemoryIndexStatusResponse]:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            result = MemoryIndexRecordRepository(session).page_for_project(
                project_id, page=page, page_size=page_size
            )
            items = [
                MemoryIndexStatusResponse(
                    id=item.id,
                    project_id=item.project_id,
                    chapter_version_id=item.chapter_version_id,
                    status=item.status,
                    attempt_count=item.attempt_count,
                    chunk_count=item.chunk_count,
                    graph_entity_count=item.graph_entity_count,
                    graph_relation_count=item.graph_relation_count,
                    embedding_provider=item.embedding_provider,
                    embedding_model=item.embedding_model,
                    embedding_dimensions=item.embedding_dimensions,
                    error_code=item.error_code,
                )
                for item in result.items
            ]
        return page_response(result, page=page, page_size=page_size, items=items)

    def list_entities(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        entity_type: GraphEntityType | None = None,
        search: str | None = None,
    ) -> PageResponse[GraphEntityResponse]:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            result = GraphEntityRepository(session).page_visible(
                project_id,
                page=page,
                page_size=page_size,
                entity_type=entity_type,
                search=search,
            )
            items = [self._graph_entity(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def get_entity(self, project_id: int, entity_id: int) -> GraphEntityResponse:
        with self._session_factory() as session:
            entity = session.get(GraphEntity, entity_id)
            if (
                entity is None
                or entity.project_id != project_id
                or entity.status is not MemoryStatus.ACCEPTED
            ):
                raise EntityNotFoundError(f"Graph entity {entity_id} was not found")
            return self._graph_entity(entity)

    def list_relations(
        self,
        project_id: int,
        *,
        current_chapter: int,
        page: int,
        page_size: int,
        predicate: GraphPredicate | None = None,
    ) -> PageResponse[GraphRelationResponse]:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)
            result = GraphRelationRepository(session).page_visible(
                project_id,
                page=page,
                page_size=page_size,
                current_chapter=current_chapter,
                predicate=predicate,
            )
            items = [self._graph_relation(item) for item in result.items]
        return page_response(result, page=page, page_size=page_size, items=items)

    def neighbors(
        self,
        project_id: int,
        entity_id: int,
        *,
        current_chapter: int,
        max_hops: int,
    ) -> GraphNeighborsResponse:
        if max_hops not in {1, 2}:
            raise DomainValidationError("Graph expansion supports one or two hops")
        with self._session_factory() as session:
            root = session.get(GraphEntity, entity_id)
            if (
                root is None
                or root.project_id != project_id
                or root.status is not MemoryStatus.ACCEPTED
            ):
                raise EntityNotFoundError(f"Graph entity {entity_id} was not found")
            repository = GraphRelationRepository(session)
            entities: dict[int, GraphEntity] = {root.id: root}
            frontier = {root.id}
            relations: dict[int, GraphRelation] = {}
            for _ in range(max_hops):
                current = repository.visible_for_entities(
                    project_id,
                    sorted(frontier),
                    current_chapter=current_chapter,
                    limit=100 - len(relations),
                )
                next_frontier: set[int] = set()
                for relation in current:
                    relations[relation.id] = relation
                    for related_id in (
                        relation.subject_entity_id,
                        relation.object_entity_id,
                    ):
                        if related_id not in entities and len(entities) < 50:
                            related = session.get(GraphEntity, related_id)
                            if related is not None and related.status is MemoryStatus.ACCEPTED:
                                entities[related.id] = related
                                next_frontier.add(related.id)
                frontier = next_frontier
                if not frontier or len(relations) >= 100:
                    break
            return GraphNeighborsResponse(
                project_id=project_id,
                entity_id=entity_id,
                current_chapter=current_chapter,
                max_hops=max_hops,
                entities=[self._graph_entity(item) for item in entities.values()],
                relations=[self._graph_relation(item) for item in relations.values()],
            )

    def _require_project(self, project_id: int) -> None:
        with self._session_factory() as session:
            self._require_project_in_session(session, project_id)

    @staticmethod
    def _require_project_in_session(session: Session, project_id: int) -> None:
        project = ProjectRepository(session).get(project_id)
        if project is None:
            raise EntityNotFoundError(f"Project {project_id} was not found")

    @staticmethod
    def _memory_summary(chunk: MemoryChunk) -> MemorySummary:
        return MemorySummary(
            id=chunk.id,
            project_id=chunk.project_id,
            chapter_id=chunk.chapter_id,
            chapter_version_id=chunk.chapter_version_id,
            source_type=chunk.source_type,
            source_id=chunk.source_id,
            chunk_index=chunk.chunk_index,
            content_preview=chunk.content[:300],
            content_hash=chunk.content_hash,
            token_estimate=chunk.token_estimate,
            character_count=chunk.character_count,
            embedding_provider=chunk.embedding_provider,
            embedding_model=chunk.embedding_model,
            embedding_dimensions=chunk.embedding_dimensions,
            status=chunk.status,
            valid_from_chapter=chunk.valid_from_chapter,
            valid_to_chapter=chunk.valid_to_chapter,
            created_at=chunk.created_at,
        )

    @staticmethod
    def _graph_entity(item: GraphEntity) -> GraphEntityResponse:
        return GraphEntityResponse(
            id=item.id,
            project_id=item.project_id,
            entity_type=item.entity_type,
            canonical_name=item.canonical_name,
            description=item.description,
            aliases=item.aliases,
            confidence=item.confidence,
            status=item.status,
            source_chapter_id=item.source_chapter_id,
            source_version_id=item.source_version_id,
        )

    @staticmethod
    def _graph_relation(item: GraphRelation) -> GraphRelationResponse:
        return GraphRelationResponse(
            id=item.id,
            project_id=item.project_id,
            subject_entity_id=item.subject_entity_id,
            subject_name=item.subject_entity.canonical_name,
            predicate=item.predicate,
            object_entity_id=item.object_entity_id,
            object_name=item.object_entity.canonical_name,
            confidence=item.confidence,
            valid_from_chapter=item.valid_from_chapter,
            valid_to_chapter=item.valid_to_chapter,
            status=item.status,
            evidence=item.evidence,
            source_version_id=item.source_version_id,
        )
