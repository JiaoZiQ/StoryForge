"""Repositories for memory chunks and index audit records."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import cast, func, or_, select
from sqlalchemy.orm import Session

from storyforge.enums import MemoryStatus
from storyforge.models import Chapter, MemoryChunk, MemoryIndexRecord
from storyforge.repositories.base import PageSlice, Repository


class MemoryChunkRepository(Repository[MemoryChunk]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MemoryChunk)

    def visible_statement(
        self,
        project_id: int,
        *,
        current_chapter: int,
        source_types: Sequence[str] = (),
    ) -> Any:
        statement = select(MemoryChunk).where(
            MemoryChunk.project_id == project_id,
            MemoryChunk.status == MemoryStatus.ACCEPTED,
            MemoryChunk.valid_from_chapter < current_chapter,
            or_(
                MemoryChunk.valid_to_chapter.is_(None),
                MemoryChunk.valid_to_chapter >= current_chapter,
            ),
        )
        if source_types:
            statement = statement.where(MemoryChunk.source_type.in_(source_types))
        return statement

    def keyword_candidates(
        self,
        project_id: int,
        *,
        current_chapter: int,
        terms: Sequence[str],
        source_types: Sequence[str] = (),
        limit: int,
    ) -> list[MemoryChunk]:
        statement = self.visible_statement(
            project_id, current_chapter=current_chapter, source_types=source_types
        )
        patterns = [MemoryChunk.content.ilike(f"%{term}%") for term in terms if term]
        if patterns:
            statement = statement.where(or_(*patterns))
        return list(
            self.session.scalars(
                statement.order_by(MemoryChunk.valid_from_chapter.desc(), MemoryChunk.id).limit(
                    limit
                )
            )
        )

    def vector_candidates(
        self,
        project_id: int,
        *,
        current_chapter: int,
        query_vector: Sequence[float],
        source_types: Sequence[str] = (),
        limit: int,
    ) -> list[tuple[MemoryChunk, float]]:
        bind = self.session.get_bind()
        if bind.dialect.name != "postgresql":
            raise RuntimeError("pgvector retrieval requires PostgreSQL")
        embedding_column = cast(MemoryChunk.embedding, VECTOR(64))
        distance = embedding_column.cosine_distance(list(query_vector)).label("distance")
        statement = self.visible_statement(
            project_id, current_chapter=current_chapter, source_types=source_types
        )
        statement = statement.add_columns(distance).order_by(distance, MemoryChunk.id).limit(limit)
        return [(row[0], float(row[1])) for row in self.session.execute(statement)]

    def get_visible(self, project_id: int, memory_id: int) -> MemoryChunk | None:
        return self.session.scalar(
            select(MemoryChunk).where(
                MemoryChunk.id == memory_id,
                MemoryChunk.project_id == project_id,
                MemoryChunk.status == MemoryStatus.ACCEPTED,
            )
        )

    def page_visible(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        source_type: str | None = None,
        chapter_number: int | None = None,
    ) -> PageSlice[MemoryChunk]:
        statement = select(MemoryChunk).where(
            MemoryChunk.project_id == project_id,
            MemoryChunk.status == MemoryStatus.ACCEPTED,
        )
        if source_type:
            statement = statement.where(MemoryChunk.source_type == source_type)
        if chapter_number is not None:
            statement = statement.join(Chapter, MemoryChunk.chapter_id == Chapter.id).where(
                Chapter.chapter_number == chapter_number
            )
        return self.paginate(statement.order_by(MemoryChunk.id), page=page, page_size=page_size)

    def duplicate_count(self, project_id: int) -> int:
        duplicate = (
            select(
                MemoryChunk.project_id,
                MemoryChunk.source_type,
                MemoryChunk.source_id,
                MemoryChunk.chunk_index,
                MemoryChunk.content_hash,
            )
            .where(MemoryChunk.project_id == project_id)
            .group_by(
                MemoryChunk.project_id,
                MemoryChunk.source_type,
                MemoryChunk.source_id,
                MemoryChunk.chunk_index,
                MemoryChunk.content_hash,
            )
            .having(func.count(MemoryChunk.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicate)) or 0


class MemoryIndexRecordRepository(Repository[MemoryIndexRecord]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, MemoryIndexRecord)

    def for_version(
        self, chapter_version_id: int, provider: str, model: str
    ) -> MemoryIndexRecord | None:
        return self.session.scalar(
            select(MemoryIndexRecord).where(
                MemoryIndexRecord.chapter_version_id == chapter_version_id,
                MemoryIndexRecord.embedding_provider == provider,
                MemoryIndexRecord.embedding_model == model,
            )
        )

    def page_for_project(
        self, project_id: int, *, page: int, page_size: int
    ) -> PageSlice[MemoryIndexRecord]:
        return self.paginate(
            select(MemoryIndexRecord)
            .where(MemoryIndexRecord.project_id == project_id)
            .order_by(MemoryIndexRecord.updated_at.desc(), MemoryIndexRecord.id.desc()),
            page=page,
            page_size=page_size,
        )
