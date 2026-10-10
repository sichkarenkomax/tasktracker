"""Settings service.

Modules read and write organization settings through this interface rather
than touching the table, so the storage backend stays replaceable
(same principle as FileService, docs/architecture.md section 43).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.settings.models import OrganizationSetting, UserSetting

#: Settings a module may declare. `default` is the value used when an
#: organization has no override stored.
SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "locale": {"type": "string", "default": "en"},
    "timezone": {"type": "string", "default": "UTC"},
    # The portal's date format. It declares its values because the browser
    # renders it directly: a stored "next tuesday" would have to be either
    # silently ignored or printed, and neither is worth the ambiguity. Keys that
    # no frontend renders stay free-form here - a module reads its own.
    "date_format": {
        "type": "string",
        "default": "YYYY-MM-DD",
        "values": ["YYYY-MM-DD", "DD.MM.YYYY", "MM/DD/YYYY", "DD.MM.YY", "locale"],
    },
    "week_starts_on": {"type": "integer", "default": 1},
    "task_auto_archive_days": {"type": "integer", "default": 0},
    # Files (stage 2.2). Zero means "no limit", which is the only honest default
    # for a self-hosted portal whose owner knows their own disk: a limit invented
    # here would be enforced the first time somebody tried to attach a file, and
    # the person hitting it would not be the person who chose the number. The
    # settings screen offers both, and per-department and per-person allowances
    # live in `storage_quotas` rather than here.
    "max_file_size_bytes": {"type": "integer", "default": 0},
    "storage_quota_bytes": {"type": "integer", "default": 0},
    # Contacts (stage 2.6): who may read another member's email, phones and
    # birthday. "everyone" is the default because a self-hosted portal is a
    # company's own installation and the person reading the profile is already
    # a colleague - a portal that hides the phone number from the team is
    # unusual rather than safe by default. An installation that wants the
    # stricter rule turns it on here, and everybody in it obeys.
    "contacts_visibility": {
        "type": "string",
        "default": "everyone",
        "values": ["everyone", "admins"],
    },
    # Whether a person may change their *own* visibility at all. This is the
    # setting the answer settled on: the portal does not decide what each member
    # shares, it decides whether they get to decide. With it off, the portal's
    # own `contacts_visibility` governs and a stored personal value is ignored
    # rather than silently winning.
    "contacts_self_service": {"type": "boolean", "default": True},
    # Presence (stage 2.9): who may read "last seen". The same two answers as
    # the contacts, and the same reasoning for the default: a self-hosted portal
    # is a team's own installation, and "when was this person here" is what a
    # colleague asks before writing to somebody at all. It is not more sensitive
    # than a phone number, and it is asked more often.
    "last_seen_visibility": {
        "type": "string",
        "default": "everyone",
        "values": ["everyone", "admins"],
    },
    # Whether a person may hide their own presence. Same division as
    # `contacts_self_service`, and with it off the portal's value governs and a
    # stored personal one is refused rather than silently winning - see
    # `PORTAL_CONTROLLED_PERSONAL_SETTINGS`.
    "last_seen_self_service": {"type": "boolean", "default": True},
}

#: Personal settings, the same contract one level down: a key declared here is a
#: key the preferences screen may write, and a key it does not declare is refused
#: rather than stored.
#:
#: `locale` and `theme` are declared because they are the settings the screen
#: actually shows. In v1 they are *read* from the browser, not from here (stage
#: 1.1: the first paint must not wait on a round trip, and a preference nobody
#: else can see has no reason to live on a server yet) - declaring them keeps the
#: screen's vocabulary in one place, so moving a key to the server later is
#: changing where the value is read, not what the screen offers.
PERSONAL_SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "locale": {"type": "string", "default": "ru", "values": ["en", "ru"]},
    "theme": {"type": "string", "default": "gold", "values": ["gold", "blue"]},
    # The date format is the first key that is *significant*: it changes what
    # people read on every screen, and two people in the same portal can want
    # different ones. So it is written here rather than in the browser, and its
    # personal value outranks the portal's.
    "date_format": {
        "type": "string",
        "default": "YYYY-MM-DD",
        "values": ["YYYY-MM-DD", "DD.MM.YYYY", "MM/DD/YYYY", "DD.MM.YY", "locale"],
    },
    # How much of a person the pickers draw (stage 2.5). Personal rather than
    # portal-wide: the position under a name is what tells two rows apart for a
    # reader who does not know the roster, and it is clutter for the colleague
    # who picks the same three people all day. `full` is the default because the
    # person choosing rarely knows everyone's titles, and a name with nothing
    # under it is the state that produces the wrong choice.
    "people_info": {
        "type": "string",
        "default": "full",
        "values": ["full", "names"],
    },
    # A person's own answer to "who may see my contacts" (stage 2.6).
    # Personal, because the portal setting only decides whether they are *allowed*
    # to answer. As with the date format, the default here is what an untouched
    # key reads as and only a stored value counts as an opinion - see
    # `users.visibility.Visibility`, which is where the two are combined.
    "contacts_visibility": {
        "type": "string",
        "default": "everyone",
        "values": ["everyone", "admins"],
    },
    # A person's own answer to "who may see that I was here" (stage 2.9).
    # Written here, and refused on write when the portal has taken the choice
    # away. The answer the roadmap question settled: this is a per-person setting,
    # and the portal decides only whether they are allowed to have one.
    "last_seen_visibility": {
        "type": "string",
        "default": "everyone",
        "values": ["everyone", "admins"],
    },
}


def defaults() -> dict[str, Any]:
    return {key: spec["default"] for key, spec in SETTING_DEFINITIONS.items()}


def definitions() -> dict[str, dict[str, Any]]:
    return dict(SETTING_DEFINITIONS)


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, organization_id: UUID) -> dict[str, Any]:
        """Effective values: definitions merged with stored overrides."""
        stmt = select(OrganizationSetting).where(
            OrganizationSetting.organization_id == organization_id
        )
        rows = (await self._session.scalars(stmt)).all()
        values = defaults()
        values.update({row.key: row.value for row in rows})
        return values

    async def write(self, organization_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(values) - set(SETTING_DEFINITIONS))
        if unknown:
            raise NotFoundError(
                f"Unknown setting(s): {', '.join(unknown)}",
                details={"available": sorted(SETTING_DEFINITIONS)},
            )

        for key, value in values.items():
            accepted = SETTING_DEFINITIONS[key].get("values")
            if accepted is not None and value not in accepted:
                raise ValidationError(
                    f"Setting {key} does not accept {value!r}",
                    details={"allowed": accepted},
                )

        stmt = select(OrganizationSetting).where(
            OrganizationSetting.organization_id == organization_id
        )
        existing = {row.key: row for row in (await self._session.scalars(stmt)).all()}

        for key, value in values.items():
            row = existing.get(key)
            if row is None:
                self._session.add(
                    OrganizationSetting(organization_id=organization_id, key=key, value=value)
                )
            else:
                row.value = value
        await self._session.flush()
        return await self.read(organization_id)


def personal_defaults() -> dict[str, Any]:
    return {key: spec["default"] for key, spec in PERSONAL_SETTING_DEFINITIONS.items()}


def personal_definitions() -> dict[str, dict[str, Any]]:
    return dict(PERSONAL_SETTING_DEFINITIONS)


#: Personal keys the portal may switch a person's right to set. Maps the
#: personal key to the organization boolean that governs it: with that setting
#: off, the portal decides and the personal row is refused on write - not ignored
#: on read, because a value that was accepted and then quietly disregarded is
#: worse than one that was never taken. The read side lives in
#: `users.visibility.Visibility`, which is where the two are combined.
PORTAL_CONTROLLED_PERSONAL_SETTINGS: dict[str, str] = {
    "contacts_visibility": "contacts_self_service",
    "last_seen_visibility": "last_seen_self_service",
}


class PersonalSettingsService:
    """One member's settings inside one organization.

    Separate from `SettingsService` rather than a flag on it: the two have
    different owners, different authority (a person may always write their own,
    while an organization's settings need a permission), and different fallbacks
    - an organization falls back to its declared default, a person falls back to
    the default *and* to whatever the browser says, which the screen resolves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, organization_id: UUID, user_id: UUID) -> dict[str, Any]:
        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id == user_id,
        )
        rows = (await self._session.scalars(stmt)).all()
        values = personal_defaults()
        values.update({row.key: row.value for row in rows})
        return values

    async def stored(self, organization_id: UUID, user_id: UUID) -> dict[str, Any]:
        """Only what this person actually chose, with no defaults merged in.

        The counterpart to `read`: an effective value cannot say whether the person
        picked it or inherited the default, and a client deciding "do they have an
        opinion of their own?" needs exactly that difference.
        """
        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id == user_id,
        )
        rows = (await self._session.scalars(stmt)).all()
        return {row.key: row.value for row in rows}

    async def stored_many(
        self, organization_id: UUID, user_ids: list[UUID]
    ) -> dict[UUID, dict[str, Any]]:
        """Several people's stored answers in one query.

        The list screens need this per page rather than per row: a roster of
        twenty-five asking the database twenty-five times is the difference
        between one screen and fifty. The result is keyed by user id, and a
        person with nothing stored is simply absent - which is what "no opinion"
        looks like from here.
        """
        if not user_ids:
            return {}
        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id.in_(user_ids),
        )
        rows = (await self._session.scalars(stmt)).all()
        answer: dict[UUID, dict[str, Any]] = {}
        for row in rows:
            answer.setdefault(row.user_id, {})[row.key] = row.value
        return answer

    async def write(
        self, organization_id: UUID, user_id: UUID, values: dict[str, Any]
    ) -> dict[str, Any]:
        unknown = sorted(set(values) - set(PERSONAL_SETTING_DEFINITIONS))
        if unknown:
            raise NotFoundError(
                f"Unknown setting(s): {', '.join(unknown)}",
                details={"available": sorted(PERSONAL_SETTING_DEFINITIONS)},
            )

        # A key may declare the values it accepts, and then a value outside that
        # list is refused here rather than stored and discovered at the first
        # render. `null` is exempt: it is how a person says "no opinion of my
        # own", which is not a value anybody has to accept.
        for key, value in values.items():
            accepted = PERSONAL_SETTING_DEFINITIONS[key].get("values")
            if value is None:
                continue
            if accepted is not None and value not in accepted:
                raise ValidationError(
                    f"Setting {key} does not accept {value!r}",
                    details={"allowed": accepted},
                )

        # Keys the portal keeps under its own hand. Refused here rather than in
        # the one screen that offers them, so no other route can write a value
        # the portal has just declared nobody may set.
        portal = await SettingsService(self._session).read(organization_id)
        blocked = sorted(
            key
            for key in values
            if key in PORTAL_CONTROLLED_PERSONAL_SETTINGS
            and not portal.get(PORTAL_CONTROLLED_PERSONAL_SETTINGS[key], True)
        )
        if blocked:
            raise PermissionDeniedError(
                f"This portal does not let members choose {', '.join(blocked)} themselves",
                details={"settings": blocked},
            )

        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id == user_id,
        )
        existing = {row.key: row for row in (await self._session.scalars(stmt)).all()}

        for key, value in values.items():
            row = existing.get(key)
            if value is None and row is not None:
                # `null` is "I have no opinion": the row goes, and the portal's
                # value (or the registry default) shows through again. Without a
                # way to say that, choosing a setting once would be permanent.
                await self._session.delete(row)
            elif row is None:
                self._session.add(
                    UserSetting(
                        organization_id=organization_id, user_id=user_id, key=key, value=value
                    )
                )
            else:
                row.value = value
        await self._session.flush()
        return await self.read(organization_id, user_id)
