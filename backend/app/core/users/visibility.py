"""Who may read another member's contacts.

Contacts are the email, the phones and the birthday (stage 2.6, data in 2.8).
The name, the department, the position and the avatar are *not* contacts: they
are how you find out who to ask, and every member of the organization reads
them. Contacts are a different thing, and the rules here are about them alone.

Three settings meet, and this module is the only place they are combined:

* the portal's ``contacts_visibility`` - ``everyone`` or ``admins``;
* the portal's ``contacts_self_service`` - may a person change their own answer?
* the person's stored ``contacts_visibility``.

The combination is deliberate rather than a chain of overrides, because each
setting answers a different question. Self-service off means the portal decides
for everybody, so a stored personal value is ignored rather than quietly
outranking it; self-service on means the person's answer is their own, and the
portal's value is what applies to everybody who never answered. That is the
question the answer settled: the portal does not decide what a member shares,
it decides whether they get to decide.

Admins see contacts in both modes. "Only admins" is a statement about the rest of
the organization, not about the administrator who has to phone somebody about a
deadline, and a mode in which an admin cannot see a phone number is a mode with
no second meaning.
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


class ContactsVisibility:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._portal = SettingsService(session)
        self._personal = PersonalSettingsService(session)

    async def self_service_allowed(self, organization_id: UUID) -> bool:
        """Whether members may change their own visibility in this portal."""
        return bool((await self._portal.read(organization_id)).get("contacts_self_service", True))

    async def effective(self, organization_id: UUID, user_id: UUID) -> str:
        """The answer that applies to one person, after both settings."""
        portal = (await self._portal.read(organization_id)).get("contacts_visibility", EVERYONE)
        if not await self.self_service_allowed(organization_id):
            return str(portal)
        stored = (await self._personal.stored(organization_id, user_id)).get("contacts_visibility")
        return str(stored) if stored in (EVERYONE, ADMINS) else str(portal)

    async def viewer_may_see(
        self,
        *,
        viewer: User,
        person_id: UUID,
        organization_id: UUID,
        viewer_role: OrganizationRole,
    ) -> bool:
        """Whether ``viewer`` may read ``person_id``'s contacts.

        Three answers, in the order that matters:

        * one's own contacts are one's own - asking whether you may read your own
          phone number would be a strange thing to have to get right;
        * an administrator may always read them, which is what makes "only
          admins" a useful mode rather than a way to hide a number from the
          people who have to use it;
        * everyone else needs the person's own answer to be "everyone".
        """
        if viewer.id == person_id:
            return True
        if is_admin(viewer_role):
            return True
        return await self.effective(organization_id, person_id) == EVERYONE
