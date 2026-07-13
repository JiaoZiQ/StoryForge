"""Declarative base classes and shared column behavior."""

from datetime import UTC, datetime

from sqlalchemy import DateTime, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


def utc_now() -> datetime:
    """Return an aware UTC timestamp for ORM-side defaults."""
    return datetime.now(UTC)


class Base(DeclarativeBase):
    """Base for every StoryForge SQLAlchemy model."""

    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class EntityBase(Base):
    """Abstract base for integer-keyed entities."""

    __abstract__ = True

    id: Mapped[int] = mapped_column(primary_key=True)


class TimestampMixin:
    """Created/updated timestamps for mutable aggregate roots."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=utc_now,
        server_default=func.now(),
        onupdate=utc_now,
        nullable=False,
    )
