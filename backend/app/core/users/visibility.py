"""Who may read another member's contacts, and when they were last here.

Two questions, one mechanism, because they are the same question asked twice:

* the contacts (stage 2.6, data in 2.8) - the email, the phones, the birthday;
* presence (stage 2.9) - whether somebody is here now, and when they were.

The name, the department, the position and the avatar are *not* either of them:
they are how you find out who to ask, and every member of the organization reads
them. Everything below is about the two that people withhold.

Three settings meet per question, and this module is the only place they are
combined:

* the portal's ``<field>_visibility`` - ``everyone`` or ``admins``;
* the portal's ``<field>_self_service`` - may a person change their own answer?
* the person's stored ``<field>_visibility``.

The combination is deliberate rather than a chain of overrides, because each
setting answers a different question. Self-service off means the portal decides
for everybody, so a stored personal value is ignored rather than quietly
outranking it; self-service on means the person's answer is their own, and the
portal's value is what applies to everybody who never answered. That is the
question the answer settled: the portal does not decide what a member shares,
it decides whether they get to decide.

Admins see both in either mode. "Only admins" is a statement about the rest of
the organization, not about the administrator who has to phone somebody about a
deadline, and a mode in which an admin cannot see a phone number is a mode with
no second meaning.

One class rather than two, parameterized by the setting names. The two questions
answer each other: the one written second is the one that would drift, and a
reader comparing them should find no logic in common - only the names.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.permissions.roles import ROLE_RANK, OrganizationRole
from app.core.settings.service import PersonalSettingsService, SettingsService
from app.core.users.models import User

#: The two answers a visibility can have. Spelled as constants rather than an
#: enum because they are settings values on both registries, and a settings
#: value that had to be cast through an enum would be stored as its name.
EVERYONE = "everyone"
ADMINS = "admins"


def is_admin(role: OrganizationRole) -> bool:
    """Admin or owner - the roles that manage the organization."""
    return ROLE_RANK[role] >= ROLE_RANK[OrganizationRole.ADMIN]


class Visibility:
    """One withheld field, under the portal's and the person's own settings.

    The names are passed in rather than hardcoded so that the second field built
    on this (presence, 2.9) reuses the rules instead of restating them. What it
    does *not* do is decide whether the setting exists: both registries declare
    their keys, and a name this class is handed that nothing declared writes
    through to the portal default, which is the same as if the portal had not
    decided anything.
    """

    def __init__(
        self,
        session: AsyncSession,
        *,
        visibility_key: str,
        self_service_key: str,
    ) -> None:
        self._session = session
        self._portal = SettingsService(session)
        self._personal = PersonalSettingsService(session)
        self._visibility_key = visibility_key
        self._self_service_key = self_service_key

    async def self_service_allowed(self, organization_id: UUID) -> bool:
        """Whether members may change their own answer in this portal."""
        return bool((await self._portal.read(organization_id)).get(self._self_service_key, True))

    async def effective(self, organization_id: UUID, user_id: UUID) -> str:
        """The answer that applies to one person, after both settings."""
        portal = (await self._portal.read(organization_id)).get(self._visibility_key, EVERYONE)
        if not await self.self_service_allowed(organization_id):
            return str(portal)
        stored = (await self._personal.stored(organization_id, user_id)).get(self._visibility_key)
        return str(stored) if stored in (EVERYONE, ADMINS) else str(portal)

    async def viewer_may_see(
        self,
        *,
        viewer: User,
        person_id: UUID,
        organization_id: UUID,
        viewer_role: OrganizationRole,
    ) -> bool:
        """Whether ``viewer`` may read this field of ``person_id``.

        Three answers, in the order that matters:

        * one's own anything is one's own - asking whether you may read your own
          phone number or your own presence would be a strange thing to have to
          get right;
        * an administrator may always read it, which is what makes "only
          admins" a useful mode rather than a way to hide a number from the
          people who have to use it;
        * everyone else needs the person's own answer to be "everyone".
        """
        if viewer.id == person_id:
            return True
        if is_admin(viewer_role):
            return True
        return await self.effective(organization_id, person_id) == EVERYONE

    async def viewer_may_see_many(
        self,
        *,
        viewer: User,
        person_ids: list[UUID],
        organization_id: UUID,
        viewer_role: OrganizationRole,
    ) -> dict[UUID, bool]:
        """The same question for a page of people, in two queries.

        The people list asks about twenty-five rows at once, and asking the
        database once per row per setting turns a roster into a hundred round
        trips. The answer is the same shape as :meth:`viewer_may_see` and is
        computed the same way - the only difference is that the portal's settings
        are read once for the page and everybody's stored answers come back in a
        single query.
        """
        if is_admin(viewer_role):
            # "Only admins" would be a mode with no second meaning otherwise.
            return dict.fromkeys(person_ids, True)
        # Your own presence is your own: it is not in this page of answers, it is
        # in the one before them.
        person_ids = [pid for pid in person_ids if pid != viewer.id]

        portal = str((await self._portal.read(organization_id)).get(self._visibility_key, EVERYONE))
        # Nobody was asked and nobody may answer: the portal answers for
        # everybody, and there is no point asking the database what nobody wrote.
        if not await self.self_service_allowed(organization_id):
            return dict.fromkeys(person_ids, portal == EVERYONE)

        stored = await self._personal.stored_many(organization_id, person_ids)
        return {
            person_id: str(stored.get(person_id, {}).get(self._visibility_key, portal)) == EVERYONE
            for person_id in person_ids
        }


def contacts_visibility(session: AsyncSession) -> Visibility:
    """The rules for the email, phones and birthday (stage 2.6)."""
    return Visibility(
        session,
        visibility_key="contacts_visibility",
        self_service_key="contacts_self_service",
    )


def presence_visibility(session: AsyncSession) -> Visibility:
    """The rules for when somebody was last here (stage 2.9)."""
    return Visibility(
        session,
        visibility_key="last_seen_visibility",
        self_service_key="last_seen_self_service",
    )
