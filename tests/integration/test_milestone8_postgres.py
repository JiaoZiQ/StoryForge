"""Real PostgreSQL pgvector and hybrid memory acceptance tests."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import Engine, make_url, select, text
from tests._factories import create_story_graph

from storyforge.api.app import create_app
from storyforge.cli.app import main
from storyforge.database import create_database_engine, create_session_factory
from storyforge.embeddings import MockEmbeddingProvider
from storyforge.enums import (
    ChapterVersionStatus,
    GraphEntityType,
    GraphPredicate,
    MemoryStatus,
)
from storyforge.m8_demo import run_demo_m8
from storyforge.memory import MemoryChunkRepository, MemoryIndexService
from storyforge.migrations import MIGRATION_HEAD
from storyforge.models import Base, ChapterVersion, GraphEntity, GraphRelation, MemoryChunk
from storyforge.retrieval import (
    FactRetriever,
    GraphRetriever,
    HybridRetrievalRequest,
    HybridRetriever,
    KeywordRetriever,
    VectorRetriever,
)
from storyforge.settings import Settings

pytestmark = pytest.mark.postgres
ROOT = Path(__file__).resolve().parents[2]


def _test_url() -> str:
    value = os.getenv("STORYFORGE_POSTGRES_TEST_URL", "")
    if not value:
        pytest.skip("STORYFORGE_POSTGRES_TEST_URL is not configured")
    if not (make_url(value).database or "").casefold().endswith("_test"):
        pytest.fail("PostgreSQL tests require a database name ending in '_test'")
    return value


@pytest.fixture(scope="module")
def pg_engine() -> Iterator[Engine]:
    database_url = _test_url()
    os.environ["DATABASE_URL"] = database_url
    config = Config(str(ROOT / "alembic.ini"))
    command.downgrade(config, "base")
    command.upgrade(config, "head")
    engine = create_database_engine(database_url)
    try:
        yield engine
    finally:
        engine.dispose()
        command.downgrade(config, "base")


@pytest.fixture(autouse=True)
def clean_database(pg_engine: Engine) -> Iterator[None]:
    tables = ", ".join(f'"{name}"' for name in Base.metadata.tables)
    with pg_engine.begin() as connection:
        connection.execute(text(f"TRUNCATE TABLE {tables} RESTART IDENTITY CASCADE"))
    yield


@pytest.fixture
def pg_settings(tmp_path: Path) -> Settings:
    return Settings(
        environment="test",
        database_url=_test_url(),
        llm_provider="mock",
        embedding_provider="mock",
        mock_mode=True,
        mock_workflow_scenario="improve",
        checkpoint_path=tmp_path / "m8-pg-checkpoints.sqlite3",
    )


@contextmanager
def _provider() -> Iterator[MockEmbeddingProvider]:
    yield MockEmbeddingProvider(dimensions=64)


def _indexer(engine: Engine) -> MemoryIndexService:
    return MemoryIndexService(
        create_session_factory(engine),
        _provider,
        provider_name="mock",
        model_name="mock-hash-embedding-v1",
        dimensions=64,
    )


def test_pgvector_extension_column_hnsw_migration_and_unique_head(pg_engine: Engine) -> None:
    with pg_engine.connect() as connection:
        assert (
            connection.scalar(text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'"))
            == 1
        )
        assert (
            connection.scalar(
                text(
                    "SELECT format_type(a.atttypid, a.atttypmod) "
                    "FROM pg_attribute a JOIN pg_class c ON c.oid = a.attrelid "
                    "WHERE c.relname = 'memory_chunks' AND a.attname = 'embedding'"
                )
            )
            == "vector(64)"
        )
        index_definition = connection.scalar(
            text(
                "SELECT indexdef FROM pg_indexes "
                "WHERE tablename = 'memory_chunks' "
                "AND indexname = 'ix_memory_chunks_embedding_hnsw'"
            )
        )
        assert index_definition is not None
        assert "USING hnsw" in index_definition
        assert "vector_cosine_ops" in index_definition
        assert connection.scalar(text("SELECT version_num FROM alembic_version")) == MIGRATION_HEAD
    command.check(Config(str(ROOT / "alembic.ini")))


def test_real_pgvector_query_is_isolated_future_safe_and_idempotent(pg_engine: Engine) -> None:
    session_factory = create_session_factory(pg_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        graph.chapter.content = graph.chapter_version.content
        project_id = graph.project.id
        version_id = graph.chapter_version.id
    indexer = _indexer(pg_engine)
    first = indexer.index_accepted_chapter_version(version_id)
    second = indexer.index_accepted_chapter_version(version_id)
    assert first.chunk_count == second.chunk_count

    vector = VectorRetriever(session_factory, _provider, dimensions=64)
    request = HybridRetrievalRequest(
        project_id=project_id,
        query="harbor turns at midnight",
        current_chapter=2,
        top_k=20,
    )
    hits = vector.retrieve(request)
    assert hits
    assert all(item.project_id == project_id for item in hits)
    assert all(item.raw_score >= 0 for item in hits)
    assert all(item.chapter_number is None or item.chapter_number < 2 for item in hits)
    assert vector.retrieve(request.model_copy(update={"project_id": project_id + 999})) == []

    with session_factory.begin() as session:
        sentinel_vector = MockEmbeddingProvider(dimensions=64).embed_query("harbor sentinel")
        for index, status in enumerate(
            (MemoryStatus.CANDIDATE, MemoryStatus.REJECTED, MemoryStatus.SUPERSEDED), start=1
        ):
            session.add(
                MemoryChunk(
                    project_id=project_id,
                    source_type="evaluation_issue",
                    source_id=f"hidden-{status.value}",
                    chunk_index=0,
                    content=f"harbor sentinel {status.value}",
                    content_hash=hashlib.sha256(status.value.encode()).hexdigest(),
                    token_estimate=5,
                    character_count=20 + index,
                    embedding=sentinel_vector,
                    embedding_provider="mock",
                    embedding_model="mock-hash-embedding-v1",
                    embedding_dimensions=64,
                    status=status,
                    valid_from_chapter=1,
                )
            )
        session.add(
            MemoryChunk(
                project_id=project_id,
                source_type="evaluation_issue",
                source_id="future",
                chunk_index=0,
                content="harbor sentinel future",
                content_hash="f" * 64,
                token_estimate=5,
                character_count=22,
                embedding=sentinel_vector,
                embedding_provider="mock",
                embedding_model="mock-hash-embedding-v1",
                embedding_dimensions=64,
                status=MemoryStatus.ACCEPTED,
                valid_from_chapter=2,
            )
        )
    filtered = vector.retrieve(
        request.model_copy(update={"query": "harbor sentinel", "top_k": 100})
    )
    assert all("sentinel" not in item.content for item in filtered)
    with session_factory() as session:
        assert MemoryChunkRepository(session).duplicate_count(project_id) == 0


def test_postgres_new_accepted_version_supersedes_old_memory(pg_engine: Engine) -> None:
    session_factory = create_session_factory(pg_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        project_id = graph.project.id
        old_id = graph.chapter_version.id
    indexer = _indexer(pg_engine)
    indexer.index_accepted_chapter_version(old_id)

    with session_factory.begin() as session:
        old = session.get(ChapterVersion, old_id)
        assert old is not None
        old.status = ChapterVersionStatus.SUPERSEDED
        revised = ChapterVersion(
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
        session.add(revised)
        session.flush()
        revised_id = revised.id
    indexer.index_accepted_chapter_version(revised_id)

    with session_factory() as session:
        assert set(
            session.scalars(
                select(MemoryChunk.status).where(MemoryChunk.chapter_version_id == old_id)
            )
        ) == {MemoryStatus.SUPERSEDED}
        assert set(
            session.scalars(
                select(MemoryChunk.status).where(MemoryChunk.chapter_version_id == revised_id)
            )
        ) == {MemoryStatus.ACCEPTED}
        assert MemoryChunkRepository(session).duplicate_count(project_id) == 0


def test_relational_graph_one_two_hop_cycle_and_future_filters(pg_engine: Engine) -> None:
    session_factory = create_session_factory(pg_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        project_id = graph.project.id
        entities: list[GraphEntity] = []
        for name in ("Alpha", "Beta", "Gamma", "Future"):
            entity = GraphEntity(
                project_id=project_id,
                entity_type=GraphEntityType.CHARACTER,
                canonical_name=name,
                normalized_name=name.casefold(),
                status=MemoryStatus.ACCEPTED,
                confidence=1,
            )
            session.add(entity)
            session.flush()
            entities.append(entity)
        edges = [
            (entities[0], entities[1], 1, MemoryStatus.ACCEPTED),
            (entities[1], entities[2], 1, MemoryStatus.ACCEPTED),
            (entities[2], entities[0], 1, MemoryStatus.ACCEPTED),
            (entities[0], entities[3], 2, MemoryStatus.ACCEPTED),
            (entities[0], entities[2], 1, MemoryStatus.REJECTED),
        ]
        for edge_index, (subject, object_, chapter, status) in enumerate(edges):
            evidence = f"edge-{edge_index}"
            session.add(
                GraphRelation(
                    project_id=project_id,
                    subject_entity_id=subject.id,
                    predicate=GraphPredicate.RELATED_TO,
                    object_entity_id=object_.id,
                    confidence=0.9,
                    valid_from_chapter=chapter,
                    status=status,
                    evidence=evidence,
                    evidence_hash=hashlib.sha256(evidence.encode()).hexdigest(),
                )
            )
    request = HybridRetrievalRequest(
        project_id=project_id,
        query="Alpha",
        current_chapter=2,
        character_names=["Alpha"],
        top_k=20,
    )
    one_hop = GraphRetriever(session_factory, max_hops=1).retrieve(request)
    two_hop = GraphRetriever(session_factory, max_hops=2).retrieve(request)
    assert one_hop
    assert len(two_hop) > len(one_hop)
    assert all("Future" not in item.content for item in two_hop)
    assert len({item.id for item in two_hop}) == len(two_hop)


def test_full_hybrid_uses_all_routes_and_graph(pg_engine: Engine) -> None:
    session_factory = create_session_factory(pg_engine)
    with session_factory.begin() as session:
        graph = create_story_graph(session)
        graph.chapter_version.content = "At midnight, the entire harbor began to turn."
        graph.chapter.content = graph.chapter_version.content
        project_id = graph.project.id
        version_id = graph.chapter_version.id
    _indexer(pg_engine).index_accepted_chapter_version(version_id)
    hybrid = HybridRetriever(
        keyword=KeywordRetriever(session_factory).retrieve,
        vector=VectorRetriever(session_factory, _provider, dimensions=64).retrieve,
        fact=FactRetriever(session_factory).retrieve,
        graph=GraphRetriever(session_factory).retrieve,
    )
    result = hybrid.retrieve(
        HybridRetrievalRequest(
            project_id=project_id,
            query="Clockwork Harbor midnight",
            current_chapter=2,
            location_names=["Clockwork Harbor"],
            top_k=20,
        )
    )
    assert result.keyword_candidates > 0
    assert result.vector_candidates > 0
    assert result.fact_candidates > 0
    assert result.graph_candidates > 0
    assert result.degraded is False
    assert result.hits
    assert result.deduplicated_count <= result.total_candidates


def test_demo_m8_api_and_cli_are_pgvector_backed_and_repeatable(
    pg_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = run_demo_m8(pg_settings)
    second = run_demo_m8(pg_settings)
    for result in (first, second):
        assert result.database_backend == "PostgreSQL"
        assert result.vector_extension == "enabled"
        assert result.embedding_provider == "mock"
        assert result.revision_attempts >= 1
        assert result.retrieval.vector_candidates > 0
        assert result.retrieval.graph_candidates > 0
        assert result.context.included_memory_hits > 0
        assert result.context.degraded_mode is False
        assert not any(result.isolation.model_dump().values())
        assert not any(result.duplicates.model_dump().values())
    assert first.project_id != second.project_id

    monkeypatch.setenv("STORYFORGE_ENVIRONMENT", "test")
    monkeypatch.setenv("STORYFORGE_DATABASE_URL", _test_url())
    monkeypatch.setenv("DATABASE_URL", _test_url())
    monkeypatch.setenv("STORYFORGE_LLM_PROVIDER", "mock")
    monkeypatch.setenv("STORYFORGE_EMBEDDING_PROVIDER", "mock")
    monkeypatch.setenv("STORYFORGE_CHECKPOINT_PATH", str(pg_settings.checkpoint_path))
    monkeypatch.delenv("STORYFORGE_LLM_API_KEY", raising=False)
    monkeypatch.delenv("STORYFORGE_EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert main(["demo-m8", "--output", "json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["vector_extension"] == "enabled"
    assert payload["retrieval"]["vector_candidates"] > 0
    assert "embedding" not in json.dumps(payload["examples"]).casefold()

    with TestClient(create_app(pg_settings)) as client:
        openapi = client.get("/openapi.json")
        assert openapi.status_code == 200
        operation_ids = [
            operation["operationId"]
            for path in openapi.json()["paths"].values()
            for operation in path.values()
        ]
        assert len(operation_ids) == len(set(operation_ids))
