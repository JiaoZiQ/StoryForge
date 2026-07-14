"""Generic SQLAlchemy repository with caller-owned transactions."""

from collections.abc import Mapping
from dataclasses import dataclass

from sqlalchemy import Select, func, inspect, select
from sqlalchemy.orm import Session

from storyforge.models.base import EntityBase


@dataclass(frozen=True, slots=True)
class PageSlice[ItemT]:
    """One database-backed page plus its unpaginated item count."""

    items: list[ItemT]
    total_items: int


class Repository[ModelT: EntityBase]:
    """Provide common CRUD operations without committing the caller's transaction."""

    def __init__(self, session: Session, model_type: type[ModelT]) -> None:
        self.session = session
        self.model_type = model_type

    def add(self, entity: ModelT) -> ModelT:
        """Add and flush an entity, preserving transaction ownership for the caller."""
        self.session.add(entity)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def get(self, entity_id: int) -> ModelT | None:
        """Return one entity by primary key."""
        return self.session.get(self.model_type, entity_id)

    def list(self, *, offset: int = 0, limit: int = 100) -> list[ModelT]:
        """Return a deterministic, bounded page ordered by primary key."""
        if offset < 0:
            raise ValueError("offset must be non-negative")
        if limit <= 0:
            raise ValueError("limit must be positive")
        statement = select(self.model_type).order_by(self.model_type.id).offset(offset).limit(limit)
        return list(self.session.scalars(statement))

    def paginate(
        self,
        statement: Select[tuple[ModelT]],
        *,
        page: int,
        page_size: int,
    ) -> PageSlice[ModelT]:
        """Execute COUNT and LIMIT/OFFSET in the database."""
        if page <= 0 or page_size <= 0:
            raise ValueError("page and page_size must be positive")
        count_statement = select(func.count()).select_from(statement.order_by(None).subquery())
        total = self.session.scalar(count_statement) or 0
        items = list(
            self.session.scalars(statement.offset((page - 1) * page_size).limit(page_size))
        )
        return PageSlice(items=items, total_items=total)

    def update(self, entity: ModelT, changes: Mapping[str, object]) -> ModelT:
        """Apply scalar column changes and flush without committing."""
        mutable_fields = {
            column.key
            for column in inspect(self.model_type).local_table.columns
            if not column.primary_key
        }
        for field_name, value in changes.items():
            if field_name not in mutable_fields:
                raise ValueError(f"Unknown or immutable field: {field_name}")
            setattr(entity, field_name, value)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def delete(self, entity: ModelT) -> None:
        """Delete an entity and flush without committing."""
        self.session.delete(entity)
        self.session.flush()
