"""Repository for user accounts.

The only module allowed to read or write the ``users`` table; everyone else
goes through :class:`~app.core.users.service.UserService`
(docs/architecture.md, sections 4-5).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import Select, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.users.models import User, UserPhone
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


class UserPhoneRepository:
    """The phones of one person.

    Separate from :class:`UserRepository` because the phone table has a
    different owner: adding a number is not an account operation, and every
    route that edits one needs nothing from the account table but the id.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for(self, user_id: UUID) -> list[UserPhone]:
        """This person's numbers, oldest first.

        The order is the creation order and nothing more - the screen shows them
        in the order they were written, because a person states which number is
        the main one by writing it first.
        """
        statement = (
            select(UserPhone)
            .where(UserPhone.user_id == user_id)
            .order_by(UserPhone.created_at, UserPhone.id)
        )
        return await fetch_all(self._session, statement)

    async def get_for_user(self, *, phone_id: UUID, user_id: UUID) -> UserPhone | None:
        """One number, but only somebody's own.

        The user id is part of the lookup rather than checked afterwards so a
        guess at somebody else's phone id returns nothing instead of a row the
        caller then has to remember to refuse.
        """
        statement = select(UserPhone).where(UserPhone.id == phone_id, UserPhone.user_id == user_id)
        return await fetch_one(self._session, statement)

    async def add(self, phone: UserPhone) -> UserPhone:
        self._session.add(phone)
        await self._session.flush()
        return phone

    async def delete(self, phone: UserPhone) -> None:
        await self._session.delete(phone)
        await self._session.flush()
