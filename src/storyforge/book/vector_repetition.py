"""PostgreSQL-backed semantic repetition candidate discovery."""

from __future__ import annotations

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import cast, select
from sqlalchemy.orm import Session, aliased

from storyforge.book.models import RepetitionCandidate, SnapshotChapter
from storyforge.enums import MemoryStatus
from storyforge.models import MemoryChunk


class PostgresVectorRepetitionDetector:
    """Use pgvector cosine distance for accepted snapshot chunks only.

    The vector match is deliberately treated as a review candidate. It never turns a
    high similarity score into a global error without the deterministic scorer and
    reviewer seeing the evidence.
    """

    def __init__(self, *, similarity_threshold: float = 0.88, maximum_candidates: int = 50) -> None:
        if not 0 < similarity_threshold <= 1:
            raise ValueError("Vector repetition similarity threshold must be in (0, 1]")
        if maximum_candidates < 1:
            raise ValueError("Vector repetition candidate limit must be positive")
        self._threshold = similarity_threshold
        self._limit = maximum_candidates

    def analyze(
        self,
        session: Session,
        *,
        project_id: int,
        chapters: list[SnapshotChapter],
    ) -> list[RepetitionCandidate]:
        bind = session.get_bind()
        if bind.dialect.name != "postgresql" or len(chapters) < 2:
            return []
        chapter_by_version = {item.chapter_version_id: item for item in chapters}
        version_ids = list(chapter_by_version)
        left = aliased(MemoryChunk)
        right = aliased(MemoryChunk)
        left_embedding = cast(left.embedding, VECTOR(64))
        right_embedding = cast(right.embedding, VECTOR(64))
        distance = left_embedding.cosine_distance(right_embedding)
        rows = session.execute(
            select(
                left.chapter_version_id,
                right.chapter_version_id,
                left.content,
                right.content,
                distance.label("cosine_distance"),
            )
            .where(
                left.project_id == project_id,
                right.project_id == project_id,
                left.status == MemoryStatus.ACCEPTED,
                right.status == MemoryStatus.ACCEPTED,
                left.chapter_version_id.in_(version_ids),
                right.chapter_version_id.in_(version_ids),
                left.chapter_version_id != right.chapter_version_id,
                left.id < right.id,
                distance <= 1 - self._threshold,
            )
            .order_by(distance, left.id, right.id)
            .limit(self._limit)
        )
        candidates: list[RepetitionCandidate] = []
        seen: set[tuple[int, int]] = set()
        for left_id, right_id, left_content, right_content, raw_distance in rows:
            if left_id is None or right_id is None:
                continue
            left_chapter = chapter_by_version.get(left_id)
            right_chapter = chapter_by_version.get(right_id)
            if left_chapter is None or right_chapter is None:
                continue
            pair = (
                min(left_chapter.chapter_number, right_chapter.chapter_number),
                max(left_chapter.chapter_number, right_chapter.chapter_number),
            )
            if pair in seen:
                continue
            seen.add(pair)
            legitimate_callback = any(
                "callback" in event.casefold() or "回环" in event
                for event in right_chapter.key_events
            )
            candidates.append(
                RepetitionCandidate(
                    code="repetition.vector_candidate",
                    severity="low" if legitimate_callback else "medium",
                    chapter_numbers=list(pair),
                    similarity=round(max(0.0, min(1.0, 1 - float(raw_distance))), 4),
                    evidence=[
                        str(left_content)[:160],
                        str(right_content)[:160],
                    ],
                    legitimate_callback=legitimate_callback,
                )
            )
        return candidates
