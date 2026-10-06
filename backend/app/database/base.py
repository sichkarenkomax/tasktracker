"""Declarative base, shared metadata and reusable model mixins."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Enum, MetaData, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.types import Uuid

# Deterministic constraint names keep Alembic autogenerate diffs stable and
# allow future batch migrations to rename constraints safely
# (docs/architecture.md, section 46).
NAMING_CONVENTION = {
    "ix": "ix_%(table_name)s_%(column_0_N_name)s",
    "uq": "uq_%(table_name)s_%(column_0_N_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


metadata = Base.metadata


def value_enum[E: StrEnum](enum_class: type[E], *, name: str, length: int) -> Enum:
    """A ``VARCHAR`` + ``CHECK`` column that stores enum *values*.

    SQLAlchemy stores member *names* by default, so a ``StrEnum`` would land in
    the database as ``"ACTIVE"`` while every ``server_default`` and API payload
    uses ``"active"`` - the generated CHECK constraint would then reject its
    own default. Pinning ``values_callable`` keeps the database, the JSON API
    and the Python enum speaking the same language.

    A plain ``VARCHAR`` with a CHECK is used rather than a native PostgreSQL
    ``ENUM`` type: adding a value later is then an ordinary constraint change
    instead of an ``ALTER TYPE`` (docs/architecture.md, section 46).
    """
    return Enum(
        enum_class,
        name=name,
        native_enum=False,
        create_constraint=True,
        length=length,
        values_callable=lambda members: [member.value for member in members],
    )


def _utcnow() -> datetime:
    return datetime.now(UTC)


class UUIDPrimaryKeyMixin:
    """Application-wide identifier: UUID v4 generated client side."""

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)


class TimestampMixin:
    """Creation and modification stamps.

    The values are computed in Python, not by ``now()`` in the database. With a
    SQL-side ``onupdate`` the ORM has to expire the attribute after every
    ``UPDATE`` and re-read it - which means an extra round trip, and a
    ``MissingGreenlet`` crash when it happens after the commit in an async
    request. ``server_default`` is kept so raw SQL and seeds still work.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=_utcnow,
        server_default=func.now(),
        onupdate=_utcnow,
    )
