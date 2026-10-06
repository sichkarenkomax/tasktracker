"""Repository for organizations, memberships and teams.

Every query is filtered by ``organization_id``: the tenant boundary is applied
in the data layer, not only in the API layer (docs/architecture.md, section 10).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.organizations.models import (
    Organization,
    OrganizationMember,
    Team,
    TeamMember,
)
from app.core.permissions.roles import OrganizationRole
from app.core.users.models import User
from app.database.helpers import count, fetch_all, fetch_one, fetch_pairs


class OrganizationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, organization_id: UUID) -> Organization | None:
        return await fetch_one(
            self._session, select(Organization).where(Organization.id == organization_id)
        )

    async def get_by_slug(self, slug: str) -> Organization | None:
        return await fetch_one(
            self._session,
            select(Organization).where(func.lower(Organization.slug) == slug.lower()),
        )

    async def slug_taken(self, slug: str, *, exclude_id: UUID | None = None) -> bool:
        existing = await self.get_by_slug(slug)
        return existing is not None and existing.id != exclude_id

    async def add(self, organization: Organization) -> Organization:
        self._session.add(organization)
        await self._session.flush()
        return organization

    async def delete(self, organization: Organization) -> None:
        await self._session.delete(organization)
        await self._session.flush()

    # --- membership -------------------------------------------------------
    async def get_member(
        self, *, organization_id: UUID, user_id: UUID
    ) -> OrganizationMember | None:
        return await fetch_one(
            self._session,
            select(OrganizationMember).where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            ),
        )

    async def list_members(self, organization_id: UUID) -> list[tuple[OrganizationMember, User]]:
        statement = (
            select(OrganizationMember, User)
            .join(User, User.id == OrganizationMember.user_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.username)
        )
        rows: list[tuple[Any, ...]] = await fetch_pairs(self._session, statement)
        return [(row[0], row[1]) for row in rows]

    async def list_for_user(self, user_id: UUID) -> list[tuple[Organization, OrganizationMember]]:
        statement = (
            select(Organization, OrganizationMember)
            .join(OrganizationMember, OrganizationMember.organization_id == Organization.id)
            .where(OrganizationMember.user_id == user_id)
            .order_by(Organization.name)
        )
        rows: list[tuple[Any, ...]] = await fetch_pairs(self._session, statement)
        return [(row[0], row[1]) for row in rows]

    async def add_member(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        role: OrganizationRole,
        invited_by_id: UUID | None = None,
    ) -> OrganizationMember:
        member = OrganizationMember(
            organization_id=organization_id,
            user_id=user_id,
            role=role,
            invited_by_id=invited_by_id,
        )
        self._session.add(member)
        await self._session.flush()
        return member

    async def remove_member(self, member: OrganizationMember) -> None:
        await self._session.delete(member)
        await self._session.flush()

    async def count_owners(self, organization_id: UUID) -> int:
        statement = (
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.role == OrganizationRole.OWNER,
            )
        )
        return await count(self._session, statement)


class TeamRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, team_id: UUID, *, organization_id: UUID) -> Team | None:
        return await fetch_one(
            self._session,
            select(Team).where(Team.id == team_id, Team.organization_id == organization_id),
        )

    async def list_for_organization(self, organization_id: UUID) -> list[Team]:
        return await fetch_all(
            self._session,
            select(Team).where(Team.organization_id == organization_id).order_by(Team.name),
        )

    async def name_taken(self, organization_id: UUID, name: str) -> bool:
        statement = (
            select(func.count())
            .select_from(Team)
            .where(
                Team.organization_id == organization_id,
                func.lower(Team.name) == name.lower(),
            )
        )
        return await count(self._session, statement) > 0

    async def add(self, team: Team) -> Team:
        self._session.add(team)
        await self._session.flush()
        return team

    async def delete(self, team: Team) -> None:
        await self._session.delete(team)
        await self._session.flush()

    async def list_member_ids(self, team_id: UUID) -> list[UUID]:
        return await fetch_all(
            self._session,
            select(TeamMember.user_id).where(TeamMember.team_id == team_id),
        )

    async def has_member(self, team_id: UUID, user_id: UUID) -> bool:
        statement = (
            select(func.count())
            .select_from(TeamMember)
            .where(TeamMember.team_id == team_id, TeamMember.user_id == user_id)
        )
        return await count(self._session, statement) > 0

    async def add_member(self, team_id: UUID, user_id: UUID) -> TeamMember:
        member = TeamMember(team_id=team_id, user_id=user_id)
        self._session.add(member)
        await self._session.flush()
        return member

    async def remove_member(self, team_id: UUID, user_id: UUID) -> bool:
        member = await fetch_one(
            self._session,
            select(TeamMember).where(TeamMember.team_id == team_id, TeamMember.user_id == user_id),
        )
        if member is None:
            return False
        await self._session.delete(member)
        await self._session.flush()
        return True
