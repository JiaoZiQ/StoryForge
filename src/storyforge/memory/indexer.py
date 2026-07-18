"""Synchronous, retryable memory and graph indexing lifecycle."""

from __future__ import annotations

import logging
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from storyforge.database import SessionFactory
from storyforge.embeddings import DATABASE_EMBEDDING_DIMENSIONS, EmbeddingProvider
from storyforge.embeddings.base import EmbeddingError
from storyforge.enums import (
    ChapterVersionStatus,
    FactStatus,
    GraphEntityType,
    MemoryIndexStatus,
    MemoryStatus,
    TaskType,
)
from storyforge.exceptions import EntityNotFoundError, InvalidStateError
from storyforge.graph import (
    ExtractedGraphEntity,
    GraphEntityRepository,
    GraphExtractor,
    GraphRelationRepository,
)
from storyforge.memory.chunker import MemoryChunker
from storyforge.memory.models import ChunkDraft, MemoryIndexResult, MemoryIndexStatusResult
from storyforge.memory.repositories import MemoryChunkRepository, MemoryIndexRecordRepository
from storyforge.models import (
    Chapter,
    ChapterVersion,
    Character,
    Fact,
    Foreshadowing,
    GraphEntity,
    GraphRelation,
    Location,
    MemoryChunk,
    MemoryIndexRecord,
    StoryRule,
)

logger = logging.getLogger(__name__)
ProviderFactory = Callable[[int, TaskType], AbstractContextManager[EmbeddingProvider]]


class MemoryIndexService:
    """Index accepted versions; provider failure leaves a retryable audit record."""

    def __init__(
        self,
        session_factory: SessionFactory,
        provider_factory: ProviderFactory,
        *,
        provider_name: str,
        model_name: str,
        dimensions: int,
        chunker: MemoryChunker | None = None,
        graph_extractor: GraphExtractor | None = None,
    ) -> None:
        if dimensions != DATABASE_EMBEDDING_DIMENSIONS:
            raise ValueError(
                f"Embedding dimensions must match database dimension {DATABASE_EMBEDDING_DIMENSIONS}"
            )
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self.provider_name = provider_name
        self.model_name = model_name
        self.dimensions = dimensions
        self._chunker = chunker or MemoryChunker()
        self._graph_extractor = graph_extractor or GraphExtractor()

    def ensure_pending(self, project_id: int, chapter_version_id: int) -> int:
        with self._session_factory.begin() as session:
            return self.ensure_pending_in_session(session, project_id, chapter_version_id)

    def ensure_pending_in_session(
        self, session: Session, project_id: int, chapter_version_id: int
    ) -> int:
        """Create the pending marker inside an existing chapter-acceptance transaction."""
        repository = MemoryIndexRecordRepository(session)
        record = repository.for_version(chapter_version_id, self.provider_name, self.model_name)
        if record is None:
            record = repository.add(
                MemoryIndexRecord(
                    project_id=project_id,
                    chapter_version_id=chapter_version_id,
                    status=MemoryIndexStatus.PENDING,
                    embedding_provider=self.provider_name,
                    embedding_model=self.model_name,
                    embedding_dimensions=self.dimensions,
                )
            )
            session.flush()
        return record.id

    def index_accepted_chapter_version(
        self, chapter_version_id: int, *, force: bool = False
    ) -> MemoryIndexResult:
        snapshot = self._load_snapshot(chapter_version_id)
        project_id, chapter, version, facts, characters, locations, rules, foreshadowing = snapshot
        record_id = self.ensure_pending(project_id, chapter_version_id)
        with self._session_factory.begin() as session:
            record = MemoryIndexRecordRepository(session).get(record_id)
            assert record is not None
            if record.status is MemoryIndexStatus.COMPLETED and not force:
                return self._result(record)
            record.status = MemoryIndexStatus.INDEXING
            record.attempt_count += 1
            record.error_code = None
            record.error_message = None
            record.updated_at = datetime.now(UTC)

        drafts = self._build_sources(
            project_id,
            chapter,
            version,
            facts,
            characters,
            locations,
            rules,
            foreshadowing,
        )
        try:
            with self._provider_factory(project_id, TaskType.EMBEDDING_DOCUMENT) as provider:
                if provider.dimensions != self.dimensions:
                    raise ValueError("Embedding provider dimension does not match database")
                vectors = provider.embed_texts([item[5].content for item in drafts])
            if len(vectors) != len(drafts) or any(len(item) != self.dimensions for item in vectors):
                raise ValueError("Embedding response shape does not match index input")
        except (EmbeddingError, ValueError) as exc:
            logger.warning(
                "memory_index_failed project_id=%s version_id=%s exception_type=%s",
                project_id,
                chapter_version_id,
                type(exc).__name__,
            )
            return self._mark_failed(record_id, type(exc).__name__)

        with self._session_factory.begin() as session:
            record = MemoryIndexRecordRepository(session).get(record_id)
            if record is None:
                raise EntityNotFoundError("Memory index record was not found")
            chunks = MemoryChunkRepository(session)
            old_version_ids = list(
                session.scalars(
                    select(ChapterVersion.id).where(
                        ChapterVersion.chapter_id == chapter.id,
                        ChapterVersion.id != version.id,
                        ChapterVersion.status == ChapterVersionStatus.SUPERSEDED,
                    )
                )
            )
            if old_version_ids:
                for old in session.scalars(
                    select(MemoryChunk).where(
                        MemoryChunk.chapter_version_id.in_(old_version_ids),
                        MemoryChunk.status == MemoryStatus.ACCEPTED,
                    )
                ):
                    old.status = MemoryStatus.SUPERSEDED
                for relation in session.scalars(
                    select(GraphRelation).where(
                        GraphRelation.source_version_id.in_(old_version_ids),
                        GraphRelation.status == MemoryStatus.ACCEPTED,
                    )
                ):
                    relation.status = MemoryStatus.SUPERSEDED
                for stale_entity in session.scalars(
                    select(GraphEntity).where(
                        GraphEntity.source_version_id.in_(old_version_ids),
                        GraphEntity.status == MemoryStatus.ACCEPTED,
                    )
                ):
                    stale_entity.status = MemoryStatus.SUPERSEDED

            current_keys: set[tuple[str, str, int, str]] = set()
            for vector_index, (
                source,
                source_id,
                source_chapter_id,
                source_version_id,
                valid_from,
                draft,
            ) in enumerate(drafts):
                key = (source, source_id, draft.chunk_index, draft.content_hash)
                current_keys.add(key)
                existing = session.scalar(
                    select(MemoryChunk).where(
                        MemoryChunk.project_id == project_id,
                        MemoryChunk.source_type == source,
                        MemoryChunk.source_id == source_id,
                        MemoryChunk.chunk_index == draft.chunk_index,
                        MemoryChunk.content_hash == draft.content_hash,
                    )
                )
                vector = vectors[vector_index]
                if existing is not None:
                    existing.embedding = vector
                    existing.status = MemoryStatus.ACCEPTED
                    existing.updated_at = datetime.now(UTC)
                    continue
                chunks.add(
                    MemoryChunk(
                        project_id=project_id,
                        chapter_id=source_chapter_id,
                        chapter_version_id=source_version_id,
                        source_type=source,
                        source_id=source_id,
                        chunk_index=draft.chunk_index,
                        content=draft.content,
                        content_hash=draft.content_hash,
                        token_estimate=draft.token_estimate,
                        character_count=draft.character_count,
                        embedding=vector,
                        embedding_provider=self.provider_name,
                        embedding_model=self.model_name,
                        embedding_dimensions=self.dimensions,
                        status=MemoryStatus.ACCEPTED,
                        valid_from_chapter=valid_from,
                        details=draft.metadata,
                    )
                )

            entity_repository = GraphEntityRepository(session)
            relation_repository = GraphRelationRepository(session)
            known_entities: dict[str, int] = {}
            for character in characters:
                entity = entity_repository.upsert(
                    project_id=project_id,
                    source_chapter_id=None,
                    source_version_id=None,
                    item=ExtractedGraphEntity(
                        entity_type=GraphEntityType.CHARACTER,
                        canonical_name=character.name,
                        description=character.description,
                        confidence=1,
                        evidence=character.description[:500],
                    ),
                )
                session.flush()
                known_entities[character.name] = entity.id
            for location in locations:
                entity = entity_repository.upsert(
                    project_id=project_id,
                    source_chapter_id=None,
                    source_version_id=None,
                    item=ExtractedGraphEntity(
                        entity_type=GraphEntityType.LOCATION,
                        canonical_name=location.name,
                        description=location.description,
                        confidence=1,
                        evidence=location.description[:500],
                    ),
                )
                session.flush()
                known_entities[location.name] = entity.id

            extraction = self._graph_extractor.extract(
                facts,
                chapter_number=chapter.chapter_number,
                content=version.content,
                character_names={item.name for item in characters},
                location_names={item.name for item in locations},
            )
            for graph_entity in extraction.entities:
                entity = entity_repository.upsert(
                    project_id=project_id,
                    source_chapter_id=chapter.id,
                    source_version_id=version.id,
                    item=graph_entity,
                )
                session.flush()
                known_entities[graph_entity.canonical_name] = entity.id
            relation_count = 0
            for graph_relation in extraction.relations:
                subject_id = known_entities.get(graph_relation.subject)
                object_id = known_entities.get(graph_relation.object)
                if subject_id is None or object_id is None or subject_id == object_id:
                    continue
                relation_repository.upsert(
                    project_id=project_id,
                    source_chapter_id=chapter.id,
                    source_version_id=version.id,
                    subject_entity_id=subject_id,
                    object_entity_id=object_id,
                    item=graph_relation,
                )
                relation_count += 1

            record.status = MemoryIndexStatus.COMPLETED
            record.chunk_count = len(drafts)
            record.graph_entity_count = len(known_entities)
            record.graph_relation_count = relation_count
            record.completed_at = datetime.now(UTC)
            record.updated_at = datetime.now(UTC)
            session.flush()
            return self._result(record)

    def supersede_version(self, chapter_version_id: int) -> None:
        with self._session_factory.begin() as session:
            self.supersede_version_in_session(session, chapter_version_id)

    @staticmethod
    def supersede_version_in_session(session: Session, chapter_version_id: int) -> None:
        """Hide old version memory atomically with the chapter pointer change."""
        for chunk in session.scalars(
            select(MemoryChunk).where(
                MemoryChunk.chapter_version_id == chapter_version_id,
                MemoryChunk.status == MemoryStatus.ACCEPTED,
            )
        ):
            chunk.status = MemoryStatus.SUPERSEDED
        for relation in session.scalars(
            select(GraphRelation).where(
                GraphRelation.source_version_id == chapter_version_id,
                GraphRelation.status == MemoryStatus.ACCEPTED,
            )
        ):
            relation.status = MemoryStatus.SUPERSEDED
        for entity in session.scalars(
            select(GraphEntity).where(
                GraphEntity.source_version_id == chapter_version_id,
                GraphEntity.status == MemoryStatus.ACCEPTED,
            )
        ):
            entity.status = MemoryStatus.SUPERSEDED

    def delete_source_index(self, project_id: int, source_type: str, source_id: str) -> int:
        with self._session_factory.begin() as session:
            records = list(
                session.scalars(
                    select(MemoryChunk).where(
                        MemoryChunk.project_id == project_id,
                        MemoryChunk.source_type == source_type,
                        MemoryChunk.source_id == source_id,
                    )
                )
            )
            for record in records:
                record.status = MemoryStatus.DELETED
            return len(records)

    def index_project_entities(self, project_id: int) -> list[MemoryIndexResult]:
        """Refresh entity-backed memory through every accepted chapter snapshot."""
        with self._session_factory() as session:
            version_ids = list(
                session.scalars(
                    select(ChapterVersion.id)
                    .join(Chapter, ChapterVersion.chapter_id == Chapter.id)
                    .where(
                        Chapter.project_id == project_id,
                        ChapterVersion.status == ChapterVersionStatus.ACCEPTED,
                    )
                    .order_by(Chapter.chapter_number, ChapterVersion.version)
                )
            )
        return [
            self.index_accepted_chapter_version(version_id, force=True)
            for version_id in version_ids
        ]

    def reindex_source(
        self, project_id: int, source_type: str, source_id: str
    ) -> list[MemoryIndexResult]:
        """Synchronously refresh the accepted version(s) owning one indexed source."""
        with self._session_factory() as session:
            version_ids = list(
                session.scalars(
                    select(MemoryChunk.chapter_version_id)
                    .where(
                        MemoryChunk.project_id == project_id,
                        MemoryChunk.source_type == source_type,
                        MemoryChunk.source_id == source_id,
                        MemoryChunk.chapter_version_id.is_not(None),
                    )
                    .distinct()
                )
            )
        return [
            self.index_accepted_chapter_version(version_id, force=True)
            for version_id in version_ids
            if version_id is not None
        ]

    def status(self, project_id: int) -> list[MemoryIndexStatusResult]:
        with self._session_factory() as session:
            records = list(
                session.scalars(
                    select(MemoryIndexRecord)
                    .where(MemoryIndexRecord.project_id == project_id)
                    .order_by(MemoryIndexRecord.id)
                )
            )
            return [self._status_result(item) for item in records]

    def get_index_status(self, project_id: int) -> list[MemoryIndexStatusResult]:
        """Named lifecycle API retained for service and adapter callers."""
        return self.status(project_id)

    def mark_version_failed(self, chapter_version_id: int, error_code: str) -> None:
        """Sanitize an unexpected post-acceptance indexing failure for later retry."""
        with self._session_factory() as session:
            record = MemoryIndexRecordRepository(session).for_version(
                chapter_version_id, self.provider_name, self.model_name
            )
            record_id = record.id if record is not None else None
        if record_id is not None:
            self._mark_failed(record_id, error_code)

    def _load_snapshot(
        self, chapter_version_id: int
    ) -> tuple[
        int,
        Chapter,
        ChapterVersion,
        list[Fact],
        list[Character],
        list[Location],
        list[StoryRule],
        list[Foreshadowing],
    ]:
        with self._session_factory() as session:
            version = session.get(ChapterVersion, chapter_version_id)
            if version is None:
                raise EntityNotFoundError("Chapter version was not found")
            if version.status is not ChapterVersionStatus.ACCEPTED:
                raise InvalidStateError("Only an accepted chapter version can be indexed")
            chapter = session.get(Chapter, version.chapter_id)
            if chapter is None:
                raise EntityNotFoundError("Chapter was not found")
            facts = list(
                session.scalars(
                    select(Fact).where(
                        Fact.chapter_version_id == version.id,
                        Fact.status == FactStatus.ACCEPTED,
                    )
                )
            )
            characters = list(
                session.scalars(select(Character).where(Character.project_id == chapter.project_id))
            )
            locations = list(
                session.scalars(select(Location).where(Location.project_id == chapter.project_id))
            )
            rules = list(
                session.scalars(
                    select(StoryRule).where(
                        StoryRule.project_id == chapter.project_id,
                        StoryRule.active.is_(True),
                    )
                )
            )
            foreshadowing = list(
                session.scalars(
                    select(Foreshadowing).where(
                        Foreshadowing.project_id == chapter.project_id,
                        Foreshadowing.setup_chapter <= chapter.chapter_number,
                    )
                )
            )
            session.expunge_all()
            return (
                chapter.project_id,
                chapter,
                version,
                facts,
                characters,
                locations,
                rules,
                foreshadowing,
            )

    def _build_sources(
        self,
        project_id: int,
        chapter: Chapter,
        version: ChapterVersion,
        facts: list[Fact],
        characters: list[Character],
        locations: list[Location],
        rules: list[StoryRule],
        foreshadowing: list[Foreshadowing],
    ) -> list[tuple[str, str, int | None, int | None, int, ChunkDraft]]:
        sources: list[tuple[str, str, int | None, int | None, int, ChunkDraft]] = []

        def add(
            source_type: str,
            source_id: str,
            content: str,
            source_chapter_id: int | None,
            source_version_id: int | None,
            valid_from: int,
            entity_names: list[str] | None = None,
        ) -> None:
            for draft in self._chunker.chunk(
                content,
                source_type=source_type,
                metadata={"entity_names": entity_names or []},
            ):
                sources.append(
                    (
                        source_type,
                        source_id,
                        source_chapter_id,
                        source_version_id,
                        valid_from,
                        draft,
                    )
                )

        add(
            "chapter_content",
            str(version.id),
            version.content,
            chapter.id,
            version.id,
            chapter.chapter_number,
            [
                *chapter.outline_metadata.get("participating_characters", []),
                *chapter.outline_metadata.get("locations", []),
            ],
        )
        add(
            "chapter_summary",
            str(version.id),
            version.summary,
            chapter.id,
            version.id,
            chapter.chapter_number,
            [
                *chapter.outline_metadata.get("participating_characters", []),
                *chapter.outline_metadata.get("locations", []),
            ],
        )
        for fact in facts:
            add(
                "fact",
                str(fact.id),
                f"{fact.subject} {fact.predicate} {fact.object}",
                chapter.id,
                version.id,
                chapter.chapter_number,
                [fact.subject, fact.object],
            )
        for character in characters:
            add(
                "character",
                str(character.id),
                f"{character.name} {character.description} {character.current_state}",
                None,
                None,
                1,
                [character.name],
            )
        for location in locations:
            add(
                "location",
                str(location.id),
                f"{location.name} {location.description}",
                None,
                None,
                1,
                [location.name],
            )
        for rule in rules:
            add("story_rule", str(rule.id), rule.statement, None, None, 1)
        for item in foreshadowing:
            add("foreshadowing", str(item.id), item.description, None, None, item.setup_chapter)
        return sources

    def _mark_failed(self, record_id: int, error_code: str) -> MemoryIndexResult:
        with self._session_factory.begin() as session:
            record = MemoryIndexRecordRepository(session).get(record_id)
            if record is None:
                raise EntityNotFoundError("Memory index record was not found")
            record.status = MemoryIndexStatus.FAILED
            record.error_code = error_code[:100]
            record.error_message = "Embedding or indexing failed; retry is available"
            record.updated_at = datetime.now(UTC)
            return self._result(record, failed=True)

    @staticmethod
    def _result(record: MemoryIndexRecord, *, failed: bool = False) -> MemoryIndexResult:
        return MemoryIndexResult(
            project_id=record.project_id,
            chapter_version_id=record.chapter_version_id,
            status="failed" if failed else "completed",
            chunk_count=record.chunk_count,
            graph_entity_count=record.graph_entity_count,
            graph_relation_count=record.graph_relation_count,
            embedding_provider=record.embedding_provider,
            embedding_model=record.embedding_model,
            embedding_dimensions=record.embedding_dimensions,
            degraded=failed,
        )

    @staticmethod
    def _status_result(record: MemoryIndexRecord) -> MemoryIndexStatusResult:
        return MemoryIndexStatusResult(
            id=record.id,
            project_id=record.project_id,
            chapter_version_id=record.chapter_version_id,
            status=record.status.value,
            attempt_count=record.attempt_count,
            chunk_count=record.chunk_count,
            graph_entity_count=record.graph_entity_count,
            graph_relation_count=record.graph_relation_count,
            embedding_provider=record.embedding_provider,
            embedding_model=record.embedding_model,
            embedding_dimensions=record.embedding_dimensions,
            error_code=record.error_code,
        )
