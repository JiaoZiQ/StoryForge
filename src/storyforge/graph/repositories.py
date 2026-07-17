"""Repository operations for the relational story graph."""

from __future__ import annotations

import hashlib
from collections.abc import Sequence

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from storyforge.enums import GraphEntityType, GraphPredicate, MemoryStatus
from storyforge.graph.models import ExtractedGraphEntity, ExtractedGraphRelation
from storyforge.graph.normalizer import GraphEntityNormalizer
from storyforge.models import GraphEntity, GraphRelation
from storyforge.repositories.base import PageSlice, Repository


class GraphEntityRepository(Repository[GraphEntity]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, GraphEntity)
        self._normalizer = GraphEntityNormalizer()

    def upsert(
        self,
        *,
        project_id: int,
        source_chapter_id: int | None,
        source_version_id: int | None,
        item: ExtractedGraphEntity,
    ) -> GraphEntity:
        normalized = self._normalizer.normalize(item.canonical_name)
        disambiguation = self._normalizer.disambiguation_key(
            entity_type=item.entity_type.value, description=item.description
        )
        existing = self.session.scalar(
            select(GraphEntity).where(
                GraphEntity.project_id == project_id,
                GraphEntity.entity_type == item.entity_type,
                GraphEntity.normalized_name == normalized,
                GraphEntity.disambiguation_key == disambiguation,
            )
        )
        if existing is not None:
            existing.status = MemoryStatus.ACCEPTED
            existing.confidence = max(existing.confidence, item.confidence)
            existing.aliases = sorted(set((*existing.aliases, *item.aliases)))
            if source_version_id is not None and existing.source_version_id is not None:
                existing.source_chapter_id = source_chapter_id
                existing.source_version_id = source_version_id
            return existing
        return self.add(
            GraphEntity(
                project_id=project_id,
                entity_type=item.entity_type,
                canonical_name=item.canonical_name,
                normalized_name=normalized,
                disambiguation_key=disambiguation,
                description=item.description,
                source_chapter_id=source_chapter_id,
                source_version_id=source_version_id,
                status=MemoryStatus.ACCEPTED,
                confidence=item.confidence,
                aliases=item.aliases,
            )
        )

    def find_visible(
        self,
        project_id: int,
        names: Sequence[str],
    ) -> list[GraphEntity]:
        normalized = [self._normalizer.normalize(item) for item in names if item.strip()]
        if not normalized:
            return []
        return list(
            self.session.scalars(
                select(GraphEntity)
                .where(
                    GraphEntity.project_id == project_id,
                    GraphEntity.status == MemoryStatus.ACCEPTED,
                    GraphEntity.normalized_name.in_(normalized),
                )
                .order_by(GraphEntity.id)
            )
        )

    def page_visible(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        entity_type: GraphEntityType | None = None,
        search: str | None = None,
    ) -> PageSlice[GraphEntity]:
        statement = select(GraphEntity).where(
            GraphEntity.project_id == project_id,
            GraphEntity.status == MemoryStatus.ACCEPTED,
        )
        if entity_type is not None:
            statement = statement.where(GraphEntity.entity_type == entity_type)
        if search:
            statement = statement.where(GraphEntity.canonical_name.ilike(f"%{search}%"))
        return self.paginate(statement.order_by(GraphEntity.id), page=page, page_size=page_size)

    def duplicate_count(self, project_id: int) -> int:
        duplicate = (
            select(
                GraphEntity.project_id,
                GraphEntity.entity_type,
                GraphEntity.normalized_name,
                GraphEntity.disambiguation_key,
            )
            .where(GraphEntity.project_id == project_id)
            .group_by(
                GraphEntity.project_id,
                GraphEntity.entity_type,
                GraphEntity.normalized_name,
                GraphEntity.disambiguation_key,
            )
            .having(func.count(GraphEntity.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicate)) or 0


class GraphRelationRepository(Repository[GraphRelation]):
    def __init__(self, session: Session) -> None:
        super().__init__(session, GraphRelation)

    def upsert(
        self,
        *,
        project_id: int,
        source_chapter_id: int,
        source_version_id: int,
        subject_entity_id: int,
        object_entity_id: int,
        item: ExtractedGraphRelation,
    ) -> GraphRelation:
        evidence_hash = hashlib.sha256(item.evidence.encode("utf-8")).hexdigest()
        existing = self.session.scalar(
            select(GraphRelation).where(
                GraphRelation.project_id == project_id,
                GraphRelation.subject_entity_id == subject_entity_id,
                GraphRelation.predicate == item.predicate,
                GraphRelation.object_entity_id == object_entity_id,
                GraphRelation.source_version_id == source_version_id,
                GraphRelation.evidence_hash == evidence_hash,
            )
        )
        if existing is not None:
            existing.status = MemoryStatus.ACCEPTED
            existing.confidence = max(existing.confidence, item.confidence)
            return existing
        return self.add(
            GraphRelation(
                project_id=project_id,
                subject_entity_id=subject_entity_id,
                predicate=item.predicate,
                object_entity_id=object_entity_id,
                source_chapter_id=source_chapter_id,
                source_version_id=source_version_id,
                confidence=item.confidence,
                valid_from_chapter=item.valid_from_chapter,
                valid_to_chapter=item.valid_to_chapter,
                status=MemoryStatus.ACCEPTED,
                evidence=item.evidence,
                evidence_hash=evidence_hash,
            )
        )

    def visible_for_entities(
        self,
        project_id: int,
        entity_ids: Sequence[int],
        *,
        current_chapter: int,
        predicates: Sequence[GraphPredicate] = (),
        limit: int = 100,
    ) -> list[GraphRelation]:
        if not entity_ids:
            return []
        statement = (
            select(GraphRelation)
            .where(
                GraphRelation.project_id == project_id,
                GraphRelation.status == MemoryStatus.ACCEPTED,
                GraphRelation.valid_from_chapter < current_chapter,
                or_(
                    GraphRelation.valid_to_chapter.is_(None),
                    GraphRelation.valid_to_chapter >= current_chapter,
                ),
                or_(
                    GraphRelation.subject_entity_id.in_(entity_ids),
                    GraphRelation.object_entity_id.in_(entity_ids),
                ),
            )
            .order_by(GraphRelation.confidence.desc(), GraphRelation.id)
            .limit(limit)
        )
        if predicates:
            statement = statement.where(GraphRelation.predicate.in_(predicates))
        return list(self.session.scalars(statement))

    def page_visible(
        self,
        project_id: int,
        *,
        page: int,
        page_size: int,
        current_chapter: int,
        predicate: GraphPredicate | None = None,
    ) -> PageSlice[GraphRelation]:
        statement = select(GraphRelation).where(
            GraphRelation.project_id == project_id,
            GraphRelation.status == MemoryStatus.ACCEPTED,
            GraphRelation.valid_from_chapter < current_chapter,
            or_(
                GraphRelation.valid_to_chapter.is_(None),
                GraphRelation.valid_to_chapter >= current_chapter,
            ),
        )
        if predicate is not None:
            statement = statement.where(GraphRelation.predicate == predicate)
        return self.paginate(statement.order_by(GraphRelation.id), page=page, page_size=page_size)

    def duplicate_count(self, project_id: int) -> int:
        duplicate = (
            select(
                GraphRelation.project_id,
                GraphRelation.subject_entity_id,
                GraphRelation.predicate,
                GraphRelation.object_entity_id,
                GraphRelation.source_version_id,
                GraphRelation.evidence_hash,
            )
            .where(GraphRelation.project_id == project_id)
            .group_by(
                GraphRelation.project_id,
                GraphRelation.subject_entity_id,
                GraphRelation.predicate,
                GraphRelation.object_entity_id,
                GraphRelation.source_version_id,
                GraphRelation.evidence_hash,
            )
            .having(func.count(GraphRelation.id) > 1)
            .subquery()
        )
        return self.session.scalar(select(func.count()).select_from(duplicate)) or 0
