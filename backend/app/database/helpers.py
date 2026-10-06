"""Small typed helpers over SQLAlchemy's async session.

``AsyncSession.scalar`` is annotated as returning ``Any``, which makes every
repository method leak ``Any`` and defeats ``mypy --strict``. These helpers keep
the declared types honest at a single place instead of scattering casts around.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any, cast

from sqlalchemy import Select
from sqlalchemy.ext.asyncio import AsyncSession


async def fetch_one[T](session: AsyncSession, statement: Select[tuple[T]]) -> T | None:
    """First row of a single-column SELECT, or ``None``."""
    return cast("T | None", await session.scalar(statement))


async def fetch_all[T](session: AsyncSession, statement: Select[tuple[T]]) -> list[T]:
    """Every row of a single-column SELECT."""
    return list((await session.scalars(statement)).all())


async def fetch_pairs(
    session: AsyncSession, statement: Select[tuple[Any, ...]]
) -> list[tuple[Any, ...]]:
    """Every row of a multi-column SELECT, as plain tuples."""
    return list(cast("Sequence[tuple[Any, ...]]", (await session.execute(statement)).all()))


async def count(session: AsyncSession, statement: Select[tuple[int]]) -> int:
    """Value of a single-cell COUNT query."""
    return int(await session.scalar(statement) or 0)
