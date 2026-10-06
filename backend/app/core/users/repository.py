"""Repository for user accounts.

The only module allowed to read or write the ``users`` table; everyone else
goes through :class:`~app.core.users.service.UserService`
(docs/architecture.md, sections 4-5).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.users.models import User
from app.database.helpers import count, fetch_all, fetch_one


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, user_id: UUID) -> User | None:
        return await fetch_one(self._session, select(User).where(User.id == user_id))

    async def get_by_email(self, email: str) -> User | None:
        statement = select(User).where(func.lower(User.email) == email.strip().lower())
        return await fetch_one(self._session, statement)

    async def get_by_username(self, username: str) -> User | None:
        statement = select(User).where(func.lower(User.username) == username.strip().lower())
        return await fetch_one(self._session, statement)

    async def exists(self, *, email: str | None = None, username: str | None = None) -> bool:
        if email is not None and await self.get_by_email(email) is not None:
            return True
        return username is not None and await self.get_by_username(username) is not None

    async def add(self, user: User) -> User:
        self._session.add(user)
        await self._session.flush()
        return user

    async def count(self) -> int:
        statement = select(func.count()).select_from(User)
        return await count(self._session, statement)

    async def search(
        self,
        *,
        term: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[User]:
        """Every account, newest first, optionally narrowed by a search term.

        This is the portal administrator's view. It is deliberately the only
        cross-tenant read of the ``users`` table in the codebase, and
        ``users.api`` guards it behind ``is_superuser`` - ordinary people browse
        each other through an organization's member list instead.
        """
        statement: Select[tuple[User]] = select(User)
        if term:
            # ILIKE rather than a trigram index: the administration list is a
            # page of fifty, not a search box somebody types into per keystroke.
            needle = f"%{term.strip()}%"
            statement = statement.where(
                or_(
                    User.email.ilike(needle),
                    User.username.ilike(needle),
                    User.first_name.ilike(needle),
                    User.last_name.ilike(needle),
                )
            )
        statement = statement.order_by(User.created_at.desc()).limit(limit).offset(offset)
        return await fetch_all(self._session, statement)
