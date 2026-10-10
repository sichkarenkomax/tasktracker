"""Service layer: the public interface other modules are allowed to call.

Services enforce permissions, mutate state and publish domain events. Routers
stay thin and never talk to the database directly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

from app.core.auth.passwords import hash_password, rehash_if_needed, verify_password
from app.core.errors import (
    ConflictError,
    CredentialsError,
    RegistrationClosedError,
    ValidationError,
)
from app.core.events.names import (
    USER_EMAIL_CHANGED,
    USER_LOGGED_IN,
    USER_PASSWORD_CHANGED,
    USER_PROFILE_UPDATED,
    USER_REGISTERED,
)
from app.core.users.models import User, UserPhone, UserStatus
from app.core.users.repository import UserPhoneRepository, UserRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


def _clean(value: str | None) -> str | None:
    """A comment that was left blank is no comment, not an empty line on screen."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


class UserService:
    def __init__(
        self,
        repository: UserRepository,
        bus: EventBus,
        phones: UserPhoneRepository,
    ) -> None:
        self._users = repository
        self._bus = bus
        self._phones = phones

    async def register(
        self,
        *,
        email: str,
        username: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
        registration_open: bool = True,
        bootstrap_superuser: bool = False,
    ) -> User:
        if not registration_open:
            raise RegistrationClosedError(
                "Registration is closed on this instance, ask an administrator for an invite"
            )
        if await self._users.exists(email=email, username=username):
            raise ConflictError("A user with this email or username already exists")

        user = User(
            email=email,
            username=username,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            status=UserStatus.ACTIVE,
        )
        # Somebody has to be the first portal administrator, and every route
        # that could grant the right already requires it. On a fresh
        # installation that first account is whichever one registers first.
        if bootstrap_superuser and await self._users.count() == 0:
            user.is_superuser = True
        await self._users.add(user)
        await self._bus.publish_event(
            USER_REGISTERED,
            actor_id=user.id,
            payload={
                "user_id": str(user.id),
                "username": user.username,
                "email": user.email,
                "summary": f"registered an account: {user.username}",
            },
        )
        return user

    async def authenticate(self, *, login: str, password: str) -> User:
        user = await self._users.get_by_email(login) or await self._users.get_by_username(login)
        if user is None or not verify_password(password, user.password_hash):
            # Same message and roughly the same work in both cases, so the
            # endpoint cannot be used to enumerate accounts.
            raise CredentialsError("Invalid credentials")

        if user.status is not UserStatus.ACTIVE:
            raise CredentialsError("This account is not active")
        if user.is_superuser:
            user.password_hash = rehash_if_needed(password, user.password_hash)

        user.last_login_at = datetime.now(UTC)
        await self._bus.publish_event(
            USER_LOGGED_IN,
            actor_id=user.id,
            payload={"username": user.username, "summary": f"{user.username} signed in"},
        )
        return user

    async def update_profile(
        self,
        user: User,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
        avatar_file_id: UUID | None = None,
    ) -> User:
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar_file_id is not None:
            # The file was checked against this very user before we got here
            # (users.api "update_me") - services trust callers inside the app,
            # the checks that face the network live at the edge.
            user.avatar_file_id = avatar_file_id
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return user

    async def set_birthday(self, user: User, *, birthday: date | None) -> User:
        """Write or clear the birthday.

        A route of its own rather than another key on ``update_profile``: that
        payload treats a missing key as "leave it alone", which for a birthday
        is not an answer - a person who wants their date *removed* has to be able
        to say null, and a shared "null means either" would make it impossible to
        keep one field while clearing another.
        """
        if birthday is not None and birthday > date.today():
            # A birthday in the future is a typo, not a date. Saying so beats
            # storing it and then computing somebody's age out of it later.
            raise ValidationError(
                "A birthday cannot be in the future", details={"field": "birthday"}
            )
        user.birthday = birthday
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return user

    async def list_phones(self, user: User) -> list[UserPhone]:
        return await self._phones.list_for(user.id)

    async def add_phone(self, user: User, *, number: str, comment: str | None = None) -> UserPhone:
        phone = UserPhone(user_id=user.id, number=number.strip(), comment=_clean(comment))
        stored = await self._phones.add(phone)
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return stored

    async def update_phone(
        self, user: User, *, phone: UserPhone, number: str, comment: str | None = None
    ) -> UserPhone:
        phone.number = number.strip()
        phone.comment = _clean(comment)
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return phone

    async def delete_phone(self, user: User, *, phone: UserPhone) -> None:
        await self._phones.delete(phone)
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )

    async def change_email(
        self, *, target: User, actor: User, organization_id: UUID, email: str
    ) -> User:
        """An administrator changes somebody's address (stage 2.7).

        No confirmation cycle: this is an administrator fixing a person's
        address, not a person claiming a new one. That is exactly why the event
        says who did it - the trail is the safeguard, and without it a wrong
        address here would be indistinguishable from a wrong address anywhere
        else. No mail is sent either way (v1 has no mail), so the person learns
        about it from the activity feed rather than from a letter nobody writes.
        """
        cleaned = email.strip()
        if not cleaned:
            raise ValidationError("Email is required", details={"field": "email"})
        existing = await self._users.get_by_email(cleaned)
        if existing is not None and existing.id != target.id:
            raise ConflictError("A user with this email already exists")

        previous = target.email
        target.email = cleaned
        # "Who changed what from what to" - the trail is the safeguard here,
        # because an address changed by an administrator reaches the person it
        # belongs to through the activity feed and nowhere else (v1 sends no
        # mail). The summary is what a reader sees, so it has to carry the whole
        # change and not just "email updated".
        summary = f"{actor.username} changed {target.username}'s email: {previous} -> {cleaned}"
        await self._bus.publish_event(
            USER_EMAIL_CHANGED,
            actor_id=actor.id,
            payload={
                "user_id": str(target.id),
                # Without this the projected row would have no organization and
                # would not appear in the feed that is its whole purpose.
                "organization_id": str(organization_id),
                "summary": summary,
                "actor": actor.username,
                "target": target.username,
                "previous_email": previous,
                "email": cleaned,
            },
        )
        return target

    async def change_password(self, user: User, *, current: str, new: str) -> None:
        if not verify_password(current, user.password_hash):
            raise ValidationError(
                "Current password is incorrect",
                details={"field": "current_password"},
            )
        user.password_hash = hash_password(new)
        await self._bus.publish_event(
            USER_PASSWORD_CHANGED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} changed their password"},
        )
