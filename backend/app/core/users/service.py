"""Service layer: the public interface other modules are allowed to call.

Services enforce permissions, mutate state and publish domain events. Routers
stay thin and never talk to the database directly.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING
from uuid import UUID

import phonenumbers

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
    USER_STATUS_CHANGED,
)
from app.core.users.models import PhoneKind, User, UserPhone, UserStatus
from app.core.users.repository import UserPhoneRepository, UserRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


def _clean(value: str | None) -> str | None:
    """A comment that was left blank is no comment, not an empty line on screen."""
    if value is None:
        return None
    trimmed = value.strip()
    return trimmed or None


def normalize_phone(number: str, country: str | None = None) -> tuple[str, str | None]:
    """The number as it is stored: E.164, and the country it was read in.

    This is Google's libphonenumber data, ported to Python - a local table of
    how numbers are written, with no network calls and nothing sent anywhere. It
    is the only thing standing between "eleven digits" and "a phone number", and
    the reason the check lives here and not in the browser: a direct call to the
    API is not obliged to pass through a form.

    ``country`` is the two letters the person chose in the UI, and it is what
    makes a *national* number ("8 900 123-45-67") parseable. Without it, and
    without a leading plus, the answer is a refusal rather than a guess: we do not
    know which country those digits belong to, and the wrong one produces a
    number that rings somebody else.
    """
    cleaned = "".join(character for character in number if character.isdigit() or character == "+")
    # A plus in the middle is a typo rather than a country prefix; keep the first
    # one and drop the rest so "+7 (900) +1 23" still stores a usable number.
    digits = cleaned.lstrip("+")
    if not 5 <= len(digits) <= 20:
        # Checked before the library so a paste accident gets the message about
        # length rather than about a country nobody mentioned.
        raise ValidationError(
            "A phone number needs between 5 and 20 digits",
            details={"field": "number", "digits": len(digits)},
        )

    region = _region(country)
    if region is None and not cleaned.startswith("+"):
        raise ValidationError(
            "A national number needs its country, and an international one needs a +",
            details={"field": "country"},
        )
    try:
        parsed = phonenumbers.parse(cleaned, region)
    except phonenumbers.NumberParseException as cause:
        raise ValidationError(
            "This is not a phone number I can read",
            details={"field": "number", "reason": str(cause)},
        ) from cause
    if not phonenumbers.is_possible_number(parsed):
        raise ValidationError(
            "This is not a possible phone number",
            details={"field": "number", "country": country},
        )
    if not phonenumbers.is_valid_number(parsed):
        raise ValidationError(
            "This phone number is not a real one",
            details={"field": "number", "country": country},
        )
    return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164), country


def _region(country: str | None) -> str | None:
    """The two letters as libphonenumber wants them, or None if they are no use.

    An unknown country is dropped rather than refused here: a number written
    with a ``+`` does not need one, and failing a row whose country was never
    recorded would make old data unreadable rather than international.
    """
    if country is None or not country.strip():
        return None
    code = country.strip().upper()
    return code if code in phonenumbers.SUPPORTED_REGIONS else None


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

    async def add_phone(
        self,
        user: User,
        *,
        number: str,
        kind: PhoneKind = PhoneKind.WORK,
        country: str | None = None,
    ) -> UserPhone:
        stored_number, stored_country = normalize_phone(number, country)
        # One person, one row per number. Two rows for the same number look like
        # a mistake from the outside - "work and mobile, same digits" - and they
        # hide each other from every list keyed by number, including the one in
        # `replace_phones`. The kind of a number is edited where it lives, not by
        # adding a second copy of it.
        existing = await self._phones.list_for(user.id)
        if any(phone.number == stored_number for phone in existing):
            raise ConflictError("This number is already on the profile")
        phone = UserPhone(user_id=user.id, number=stored_number, kind=kind, country=stored_country)
        stored = await self._phones.add(phone)
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return stored

    async def update_phone(
        self, user: User, *, phone: UserPhone, number: str, kind: PhoneKind, country: str | None
    ) -> UserPhone:
        stored_number, stored_country = normalize_phone(number, country)
        # The same rule as on adding, with this row itself taken out of the way:
        # renaming a number to itself is not a duplicate.
        if any(
            other.number == stored_number and other.id != phone.id
            for other in await self._phones.list_for(user.id)
        ):
            raise ConflictError("This number is already on the profile")
        phone.number = stored_number
        phone.country = stored_country
        phone.kind = kind
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )
        return phone

    async def replace_phones(
        self, user: User, *, numbers: list[tuple[str, PhoneKind, str | None]]
    ) -> list[UserPhone]:
        """An administrator writes somebody else's whole set of numbers.

        A full replacement rather than add/remove calls, for the same reason the
        profile editor is one route: three requests leave the person with half
        of what the administrator typed, and a list is the only shape that can be
        checked before anything is written. Rows the administrator did not list
        are removed - which is what "the set is these three" means.

        The ids are preserved where a row already exists, so a number nobody
        touched keeps its place and its row id, and a notification about it
        (stage 5) keeps pointing at the same thing.
        """
        # Everything is normalized first: one impossible number in the list
        # refuses the whole request, rather than leaving the person with the
        # first two numbers written and the third not.
        normalized = [normalize_phone(number, country) for number, _kind, country in numbers]
        stored = {
            number: (country, kind)
            for (number, country), (_number, kind, _country) in zip(
                normalized, numbers, strict=True
            )
        }
        # Walked as a list, not as a dict keyed by the number. Two rows for one
        # number can only be a leftover from before the unique index, but a
        # replacement that silently left one of them behind would be a bug in
        # this method rather than in the data, so the second row is deleted
        # here too.
        existing = await self._phones.list_for(user.id)
        consumed: set[str] = set()
        for phone in existing:
            entry = stored.get(phone.number)
            if entry is None or phone.number in consumed:
                await self._phones.delete(phone)
                continue
            consumed.add(phone.number)
            phone.country, phone.kind = entry

        for number, (country, kind) in stored.items():
            if number not in consumed:
                await self._phones.add(
                    UserPhone(user_id=user.id, number=number, kind=kind, country=country)
                )

        if numbers:
            await self._bus.publish_event(
                USER_PROFILE_UPDATED,
                actor_id=user.id,
                payload={
                    "user_id": str(user.id),
                    "summary": f"{user.username} updated their profile",
                },
            )
        return await self._phones.list_for(user.id)

    async def delete_phone(self, user: User, *, phone: UserPhone) -> None:
        await self._phones.delete(phone)
        await self._bus.publish_event(
            USER_PROFILE_UPDATED,
            actor_id=user.id,
            payload={"user_id": str(user.id), "summary": f"{user.username} updated their profile"},
        )

    async def set_status(
        self, *, target: User, status: UserStatus, actor: User, organization_id: UUID
    ) -> User:
        """Lock or unlock an account (stage 2.18).

        A disabled account stops signing in everywhere, not only here, which is
        why the caller has to be a portal administrator rather than the owner of
        one organization: an administrator of one tenant must not be able to lock
        somebody out of another one.

        The event carries both the organization that asked and the account, so
        the trail is readable from either side. No letter: v1 sends none, which
        leaves the activity feed as how the person finds out that their login
        stopped working.
        """
        previous = target.status
        target.status = status
        await self._bus.publish_event(
            USER_STATUS_CHANGED,
            actor_id=actor.id,
            payload={
                "user_id": str(target.id),
                "organization_id": str(organization_id),
                "from_status": str(previous),
                "to_status": str(status),
                "summary": (
                    f"{actor.username} set {target.username}'s status: {previous} -> {status}"
                ),
            },
        )
        return target

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
