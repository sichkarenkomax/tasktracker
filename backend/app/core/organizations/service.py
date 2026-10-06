"""Organization, membership and team services.

This is the public interface other modules are allowed to call. Nothing outside
Core may write to these tables directly.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.events.names import (
    ORGANIZATION_CREATED,
    ORGANIZATION_DELETED,
    ORGANIZATION_MEMBER_ADDED,
    ORGANIZATION_MEMBER_REMOVED,
    ORGANIZATION_MEMBER_ROLE_CHANGED,
    ORGANIZATION_UPDATED,
    TEAM_CREATED,
    TEAM_DELETED,
    TEAM_MEMBER_ADDED,
    TEAM_MEMBER_REMOVED,
    TEAM_UPDATED,
)
from app.core.organizations.models import Organization, OrganizationMember, Team
from app.core.organizations.repository import OrganizationRepository, TeamRepository
from app.core.permissions.roles import OrganizationRole
from app.core.users.models import User
from app.core.users.repository import UserRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


class OrganizationService:
    def __init__(
        self,
        organizations: OrganizationRepository,
        users: UserRepository,
        bus: EventBus,
    ) -> None:
        self._organizations = organizations
        self._users = users
        self._bus = bus

    async def create(
        self,
        *,
        owner: User,
        name: str,
        slug: str,
        description: str | None = None,
    ) -> Organization:
        if await self._organizations.slug_taken(slug):
            raise ConflictError(f"Organization slug '{slug}' is already in use")

        organization = await self._organizations.add(
            Organization(name=name, slug=slug, description=description)
        )
        # The creator must be able to manage what they just created.
        await self._organizations.add_member(
            organization_id=organization.id,
            user_id=owner.id,
            role=OrganizationRole.OWNER,
            invited_by_id=owner.id,
        )
        await self._bus.publish_event(
            ORGANIZATION_CREATED,
            actor_id=owner.id,
            payload={
                "organization_id": str(organization.id),
                "name": organization.name,
                "slug": organization.slug,
                "summary": f"created organization {organization.name!r}",
            },
        )
        return organization

    async def update(
        self, organization: Organization, *, actor: User, **changes: object
    ) -> Organization:
        changed: list[str] = []
        for field in ("name", "description"):
            value = changes.get(field)
            if value is not None:
                setattr(organization, field, value)
                changed.append(field)
        if changed:
            await self._bus.publish_event(
                ORGANIZATION_UPDATED,
                actor_id=actor.id,
                payload={
                    "organization_id": str(organization.id),
                    "changed": changed,
                    "summary": f"updated {', '.join(changed)} of organization "
                    f"{organization.name!r}",
                },
            )
        return organization

    async def delete(self, organization: Organization, *, actor: User) -> None:
        organization_id = organization.id
        name = organization.name
        await self._organizations.delete(organization)
        await self._bus.publish_event(
            ORGANIZATION_DELETED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "summary": f"deleted organization {name!r}",
            },
        )

    # --- membership -----------------------------------------------------
    async def add_member(
        self,
        *,
        organization: Organization,
        actor: User,
        role: OrganizationRole,
        user_id: UUID | None = None,
        email: str | None = None,
    ) -> OrganizationMember:
        if (user_id is None) == (email is None):
            raise ValidationError("Provide exactly one of user_id or email")

        if user_id is not None:
            target = await self._users.get(user_id)
        else:
            target = await self._users.get_by_email(email or "")
        if target is None:
            raise NotFoundError("No user matches the supplied identifier")

        if await self._organizations.get_member(organization_id=organization.id, user_id=target.id):
            raise ConflictError(f"{target.username} is already a member")

        member = await self._organizations.add_member(
            organization_id=organization.id,
            user_id=target.id,
            role=role,
            invited_by_id=actor.id,
        )
        await self._bus.publish_event(
            ORGANIZATION_MEMBER_ADDED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization.id),
                "user_id": str(target.id),
                "role": str(role),
                "summary": f"added {target.username} as {role}",
            },
        )
        return member

    async def change_member_role(
        self,
        *,
        organization: Organization,
        member: OrganizationMember,
        new_role: OrganizationRole,
        actor: User,
    ) -> OrganizationMember:
        if (
            member.role is OrganizationRole.OWNER
            and new_role is not OrganizationRole.OWNER
            and await self._organizations.count_owners(organization.id) <= 1
        ):
            raise ValidationError("An organization must keep at least one owner")
        previous = member.role
        member.role = new_role
        await self._bus.publish_event(
            ORGANIZATION_MEMBER_ROLE_CHANGED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization.id),
                "user_id": str(member.user_id),
                "from_role": str(previous),
                "to_role": str(new_role),
                "summary": f"changed a member's role: {previous} -> {new_role}",
            },
        )
        return member

    async def remove_member(
        self, *, organization: Organization, member: OrganizationMember, actor: User
    ) -> None:
        if (
            member.role is OrganizationRole.OWNER
            and (await self._organizations.count_owners(organization.id)) <= 1
        ):
            raise ValidationError("An organization must keep at least one owner")

        user_id = member.user_id
        organization_id = organization.id
        await self._organizations.remove_member(member)
        await self._bus.publish_event(
            ORGANIZATION_MEMBER_REMOVED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "summary": "removed a member",
            },
        )


class TeamService:
    def __init__(self, teams: TeamRepository, bus: EventBus) -> None:
        self._teams = teams
        self._bus = bus

    async def create(
        self, *, organization_id: UUID, actor: User, name: str, description: str | None = None
    ) -> Team:
        if await self._teams.name_taken(organization_id, name):
            raise ConflictError(f"A team named '{name}' already exists")

        team = await self._teams.add(
            Team(organization_id=organization_id, name=name, description=description)
        )
        await self._bus.publish_event(
            TEAM_CREATED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "team_id": str(team.id),
                "name": team.name,
                "summary": f"created team {team.name!r}",
            },
        )
        return team

    async def update(self, team: Team, *, actor: User, **changes: object) -> Team:
        changed: list[str] = []
        for field in ("name", "description"):
            value = changes.get(field)
            if value is not None:
                setattr(team, field, value)
                changed.append(field)
        if changed:
            await self._bus.publish_event(
                TEAM_UPDATED,
                actor_id=actor.id,
                payload={
                    "team_id": str(team.id),
                    "organization_id": str(team.organization_id),
                    "summary": f"updated {', '.join(changed)} of team {team.name!r}",
                },
            )
        return team

    async def delete(self, team: Team, *, actor: User) -> None:
        team_id, organization_id = team.id, team.organization_id
        name = team.name
        await self._teams.delete(team)
        await self._bus.publish_event(
            TEAM_DELETED,
            actor_id=actor.id,
            payload={
                "team_id": str(team_id),
                "organization_id": str(organization_id),
                "summary": f"deleted team {name!r}",
            },
        )

    async def add_member(self, team: Team, *, actor: User, user_id: UUID) -> None:
        if await self._teams.has_member(team.id, user_id):
            raise ConflictError("User is already a member of this team")
        await self._teams.add_member(team.id, user_id)
        await self._bus.publish_event(
            TEAM_MEMBER_ADDED,
            actor_id=actor.id,
            payload={
                "team_id": str(team.id),
                "organization_id": str(team.organization_id),
                "user_id": str(user_id),
                "summary": f"added a member to team {team.name!r}",
            },
        )

    async def remove_member(self, team: Team, *, actor: User, user_id: UUID) -> None:
        if not await self._teams.remove_member(team.id, user_id):
            raise NotFoundError("User is not a member of this team")
        await self._bus.publish_event(
            TEAM_MEMBER_REMOVED,
            actor_id=actor.id,
            payload={
                "team_id": str(team.id),
                "organization_id": str(team.organization_id),
                "user_id": str(user_id),
                "summary": f"removed a member from team {team.name!r}",
            },
        )
