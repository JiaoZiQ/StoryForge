"""SQLite fallback lifecycle coverage without pretending to run pgvector."""

from __future__ import annotations

from collections import deque
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, func, select
from tests._factories import create_story_graph

from storyforge.database import create_session_factory
from storyforge.embeddings import MockEmbeddingFailure, MockEmbeddingProvider
from storyforge.enums import ChapterVersionStatus, MemoryIndexStatus, MemoryStatus, TaskType
from storyforge.memory import MemoryChunkRepository, MemoryIndexService
from storyforge.models import ChapterVersion, GraphRelation, MemoryChunk, MemoryIndexRecord
from storyforge.retrieval import HybridRetrievalRequest, KeywordRetriever, VectorRetriever
from storyforge.retrieval.models import RetrieverUnavailableError


@contextmanager
def _mock_provider(_project_id: int, _task_type: TaskType) -> Iterator[MockEmbeddingProvider]:
    yield MockEmbeddingProvider(dimensions=64)


def test_memory_index_is_idempotent_visible_and_graph_backed(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        graph.chapter.content = graph.chapter_version.content
        version_id = graph.chapter_version.id
        project_id = graph.project.id

    service = MemoryIndexService(
        session_factory,
        _mock_provider,
        provider_name="mock",
        model_name="mock-hash-embedding-v1",
        dimensions=64,
    )
    first = service.index_accepted_chapter_version(version_id)
    second = service.index_accepted_chapter_version(version_id)
    assert first.status == second.status == "completed"
    assert first.chunk_count >= 5
    assert first.graph_relation_count == 1

    request = HybridRetrievalRequest(
        project_id=project_id,
        query="harbor midnight",
        current_chapter=2,
        top_k=20,
    )
    keyword = KeywordRetriever(session_factory).retrieve(request)
    assert keyword
    assert all(item.chapter_number is None or item.chapter_number < 2 for item in keyword)
    with pytest.raises(RetrieverUnavailableError, match="PostgreSQL"):
        VectorRetriever(session_factory, _mock_provider, dimensions=64).retrieve(request)

    with session_factory() as session:
        assert MemoryChunkRepository(session).duplicate_count(project_id) == 0
        assert session.scalar(select(func.count(GraphRelation.id))) == 1
        record = session.scalar(select(MemoryIndexRecord))
        assert record is not None
        assert record.status is MemoryIndexStatus.COMPLETED
        assert record.attempt_count == 1


def test_memory_failure_is_retryable_and_does_not_change_accepted_version(
    db_engine: Engine,
) -> None:
    session_factory = create_session_factory(db_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        version_id = graph.chapter_version.id
        project_id = graph.project.id

    providers = deque(
        [
            MockEmbeddingProvider(
                dimensions=64,
                failures=[MockEmbeddingFailure.TIMEOUT],
            ),
            MockEmbeddingProvider(dimensions=64),
        ]
    )

    @contextmanager
    def provider(_project_id: int, _task_type: TaskType) -> Iterator[MockEmbeddingProvider]:
        yield providers.popleft()

    service = MemoryIndexService(
        session_factory,
        provider,
        provider_name="mock",
        model_name="mock-hash-embedding-v1",
        dimensions=64,
    )
    failed = service.index_accepted_chapter_version(version_id)
    assert failed.status == "failed"
    with session_factory() as session:
        record = session.scalar(select(MemoryIndexRecord))
        assert record is not None and record.status is MemoryIndexStatus.FAILED
        assert "timed out" not in (record.error_message or "").casefold()
        assert session.scalar(select(func.count(MemoryChunk.id))) == 0
    completed = service.index_accepted_chapter_version(version_id)
    assert completed.status == "completed"
    assert completed.chunk_count > 0
    assert service.status(project_id)[0].attempt_count == 2


def test_memory_status_filters_delete_and_supersede(db_engine: Engine) -> None:
    session_factory = create_session_factory(db_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        version_id = graph.chapter_version.id
        project_id = graph.project.id
    service = MemoryIndexService(
        session_factory,
        _mock_provider,
        provider_name="mock",
        model_name="mock-hash-embedding-v1",
        dimensions=64,
    )
    service.index_accepted_chapter_version(version_id)
    with session_factory.begin() as session:
        session.add(
            MemoryChunk(
                project_id=project_id,
                source_type="evaluation_issue",
                source_id="candidate-1",
                chunk_index=0,
                content="candidate secret",
                content_hash="c" * 64,
                token_estimate=4,
                character_count=16,
                embedding=[0.0] * 64,
                embedding_provider="mock",
                embedding_model="mock-hash-embedding-v1",
                embedding_dimensions=64,
                status=MemoryStatus.CANDIDATE,
                valid_from_chapter=1,
            )
        )
    visible = KeywordRetriever(session_factory).retrieve(
        HybridRetrievalRequest(
            project_id=project_id,
            query="candidate secret",
            current_chapter=2,
        )
    )
    assert visible == []
    assert service.delete_source_index(project_id, "evaluation_issue", "candidate-1") == 1
    service.supersede_version(version_id)
    with session_factory() as session:
        version_chunks = list(
            session.scalars(select(MemoryChunk).where(MemoryChunk.chapter_version_id == version_id))
        )
        assert version_chunks
        assert {item.status for item in version_chunks} == {MemoryStatus.SUPERSEDED}
        deleted = session.scalar(select(MemoryChunk).where(MemoryChunk.source_id == "candidate-1"))
        assert deleted is not None and deleted.status is MemoryStatus.DELETED


def test_indexing_new_accepted_version_supersedes_old_version_memory(
    db_engine: Engine,
) -> None:
    session_factory = create_session_factory(db_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        project_id = graph.project.id
        old_id = graph.chapter_version.id
    service = MemoryIndexService(
        session_factory,
        _mock_provider,
        provider_name="mock",
        model_name="mock-hash-embedding-v1",
        dimensions=64,
    )
    service.index_accepted_chapter_version(old_id)
    with session_factory.begin() as session:
        old = session.get(ChapterVersion, old_id)
        assert old is not None
        old.status = ChapterVersionStatus.SUPERSEDED
        new = ChapterVersion(
            chapter_id=old.chapter_id,
            version=2,
            title="Revised harbor",
            content="The harbor remained still until Mara turned the key.",
            summary="Mara stops the moving harbor.",
            status=ChapterVersionStatus.ACCEPTED,
            source="revision",
            parent_version_id=old.id,
            word_count=9,
            provider="mock",
            model="mock",
        )
        session.add(new)
        session.flush()
        new_id = new.id
    service.index_accepted_chapter_version(new_id)
    with session_factory() as session:
        old_statuses = set(
            session.scalars(
                select(MemoryChunk.status).where(MemoryChunk.chapter_version_id == old_id)
            )
        )
        new_statuses = set(
            session.scalars(
                select(MemoryChunk.status).where(MemoryChunk.chapter_version_id == new_id)
            )
        )
        assert old_statuses == {MemoryStatus.SUPERSEDED}
        assert new_statuses == {MemoryStatus.ACCEPTED}
        assert MemoryChunkRepository(session).duplicate_count(project_id) == 0
