"""Service layer: the public interface other modules are allowed to call.

Services enforce permissions, mutate state and publish domain events. Routers
stay thin and never talk to the database directly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from app.core.auth.passwords import hash_password, rehash_if_needed, verify_password
from app.core.errors import (
    ConflictError,
    CredentialsError,
    RegistrationClosedError,
    ValidationError,
)
from app.core.events.names import (
    USER_LOGGED_IN,
    USER_PASSWORD_CHANGED,
    USER_PROFILE_UPDATED,
    USER_REGISTERED,
)
from app.core.users.models import User, UserStatus
from app.core.users.repository import UserRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


class UserService:
    def __init__(self, repository: UserRepository, bus: EventBus) -> None:
        self._users = repository
        self._bus = bus

    async def register(
        self,
        *,
        email: str,
        username: str,
        password: str,
        first_name: str | None = None,
        last_name: str | None = None,
        registration_open: bool = True,
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
        avatar_url: str | None = None,
    ) -> User:
        if first_name is not None:
            user.first_name = first_name
        if last_name is not None:
            user.last_name = last_name
        if avatar_url is not None:
            user.avatar_url = avatar_url
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return user

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
