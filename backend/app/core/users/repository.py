"""Repository for user accounts.

The only module allowed to read or write the ``users`` table; everyone else
goes through :class:`~app.core.users.service.UserService`
(docs/architecture.md, sections 4-5).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.users.models import User
from app.database.helpers import count, fetch_one


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
