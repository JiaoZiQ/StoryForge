"""PostgreSQL pgvector, graph, and hybrid retrieval demonstration."""

from __future__ import annotations

from uuid import uuid4

from sqlalchemy import func, make_url, select, text
from sqlalchemy.orm import Session

from storyforge.application import (
    DemoApplicationService,
    DomainServiceFactory,
    MemoryApplicationService,
    SystemApplicationService,
)
from storyforge.database import (
    create_database_engine,
    create_session_factory,
    normalize_database_url,
)
from storyforge.enums import MemoryStatus
from storyforge.exceptions import ConfigurationError, InvalidStateError
from storyforge.graph import GraphEntityRepository, GraphRelationRepository
from storyforge.memory import MemoryChunkRepository
from storyforge.models import GraphEntity, GraphRelation, MemoryChunk, MemoryIndexRecord
from storyforge.schemas.api import MemoryReindexRequest, RetrievalSearchRequest
from storyforge.schemas.context import ContextBuildRequest
from storyforge.schemas.retrieval import (
    DemoM8Context,
    DemoM8Duplicates,
    DemoM8Example,
    DemoM8Isolation,
    DemoM8Response,
    DemoM8Retrieval,
)
from storyforge.settings import Settings


def run_demo_m8(settings: Settings | None = None) -> DemoM8Response:
    """Run a network-free M8 flow against a real PostgreSQL pgvector database."""
    configured = settings or Settings.from_env()
    backend = make_url(normalize_database_url(configured.database_url)).get_backend_name()
    if backend != "postgresql":
        raise ConfigurationError("demo-m8 requires a PostgreSQL database")
    if configured.llm_provider != "mock" or configured.embedding_provider != "mock":
        raise ConfigurationError("demo-m8 requires MockLLM and MockEmbedding")
    if configured.llm_api_key is not None or configured.embedding_api_key is not None:
        raise ConfigurationError("demo-m8 must run without API keys")

    engine = create_database_engine(configured.database_url)
    try:
        session_factory = create_session_factory(engine)
        SystemApplicationService(session_factory, configured).readiness()
        with engine.connect() as connection:
            extension = connection.scalar(
                text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
            )
        if not extension:
            raise InvalidStateError("PostgreSQL vector extension is not enabled")

        demo = DemoApplicationService(session_factory, configured).run(
            project_title=f"Milestone 8 Hybrid RAG {uuid4().hex[:12]}"
        )
        project_id = demo.project.id
        accepted_pointer = demo.chapter.accepted_version
        if accepted_pointer is None:
            raise InvalidStateError("demo-m8 workflow has no accepted version")

        factory = DomainServiceFactory(session_factory, configured)
        memory = MemoryApplicationService(session_factory, factory, configured)
        reindex_request = MemoryReindexRequest(
            chapter_version_id=accepted_pointer.id,
            force=False,
        )
        memory.reindex(project_id, reindex_request)
        memory.reindex(project_id, reindex_request)

        entities = memory.list_entities(project_id, page=1, page_size=100)
        character_names = [
            item.canonical_name for item in entities.items if item.entity_type.value == "character"
        ]
        character_names = list(dict.fromkeys((*character_names, "Mara")))
        search = memory.search(
            project_id,
            RetrievalSearchRequest(
                query="Mara brass key",
                current_chapter=2,
                character_names=character_names,
                top_k=20,
                max_context_chars=16_000,
            ),
        )
        context = factory.context_builder().build(
            ContextBuildRequest(project_id=project_id, chapter_number=2)
        )

        visible_ids = {
            item.id for item in search.hits if item.source_type not in {"fact", "graph_relation"}
        }
        with session_factory() as session:
            chunk_count = (
                session.scalar(
                    select(func.count(MemoryChunk.id)).where(
                        MemoryChunk.project_id == project_id,
                        MemoryChunk.status == MemoryStatus.ACCEPTED,
                    )
                )
                or 0
            )
            entity_count = (
                session.scalar(
                    select(func.count(GraphEntity.id)).where(
                        GraphEntity.project_id == project_id,
                        GraphEntity.status == MemoryStatus.ACCEPTED,
                    )
                )
                or 0
            )
            relation_count = (
                session.scalar(
                    select(func.count(GraphRelation.id)).where(
                        GraphRelation.project_id == project_id,
                        GraphRelation.status == MemoryStatus.ACCEPTED,
                    )
                )
                or 0
            )
            isolation = DemoM8Isolation(
                candidate_chunks_visible=_visible_status_count(
                    session, project_id, visible_ids, MemoryStatus.CANDIDATE
                ),
                rejected_chunks_visible=_visible_status_count(
                    session, project_id, visible_ids, MemoryStatus.REJECTED
                ),
                superseded_chunks_visible=_visible_status_count(
                    session, project_id, visible_ids, MemoryStatus.SUPERSEDED
                ),
                future_chunks_visible=session.scalar(
                    select(func.count(MemoryChunk.id)).where(
                        MemoryChunk.project_id == project_id,
                        MemoryChunk.id.in_(visible_ids),
                        MemoryChunk.valid_from_chapter >= 2,
                    )
                )
                or 0,
            )
            duplicates = DemoM8Duplicates(
                memory_chunks=MemoryChunkRepository(session).duplicate_count(project_id),
                graph_entities=GraphEntityRepository(session).duplicate_count(project_id),
                graph_relations=GraphRelationRepository(session).duplicate_count(project_id),
            )
            reindex_attempts = (
                session.scalar(
                    select(MemoryIndexRecord.attempt_count).where(
                        MemoryIndexRecord.chapter_version_id == accepted_pointer.id
                    )
                )
                or 0
            )

        if search.vector_candidates < 1:
            raise InvalidStateError("demo-m8 did not execute a successful pgvector query")
        if not search.hits or not context.memory_hits:
            raise InvalidStateError("demo-m8 did not retrieve accepted chapter-one memory")
        if any(isolation.model_dump().values()) or any(duplicates.model_dump().values()):
            raise InvalidStateError("demo-m8 detected isolation or idempotency failure")

        return DemoM8Response(
            database_backend="PostgreSQL",
            vector_extension="enabled",
            embedding_provider="mock",
            embedding_dimensions=configured.embedding_dimensions,
            project_id=project_id,
            workflow_status=demo.workflow.status.value,
            accepted_version=demo.accepted_version,
            revision_attempts=demo.workflow.revision_attempt,
            memory_chunks=chunk_count,
            graph_entities=entity_count,
            graph_relations=relation_count,
            retrieval=DemoM8Retrieval(
                keyword_candidates=search.keyword_candidates,
                vector_candidates=search.vector_candidates,
                fact_candidates=search.fact_candidates,
                graph_candidates=search.graph_candidates,
                deduplicated_count=search.deduplicated_count,
                final_hits=len(search.hits),
            ),
            context=DemoM8Context(
                included_memory_hits=len(context.memory_hits),
                estimated_characters=context.budget.estimated_chars,
                degraded_mode=context.budget.retrieval_degraded,
            ),
            isolation=isolation,
            duplicates=duplicates,
            reindex_attempts=reindex_attempts,
            examples=[
                DemoM8Example(
                    source_type=item.source_type,
                    sources=item.sources,
                    score=item.score,
                    explanation=item.explanation,
                )
                for item in search.hits[:3]
            ],
        )
    finally:
        engine.dispose()


def _visible_status_count(
    session: Session,
    project_id: int,
    visible_ids: set[int],
    status: MemoryStatus,
) -> int:
    return (
        session.scalar(
            select(func.count(MemoryChunk.id)).where(
                MemoryChunk.project_id == project_id,
                MemoryChunk.id.in_(visible_ids),
                MemoryChunk.status == status,
            )
        )
        or 0
    )
