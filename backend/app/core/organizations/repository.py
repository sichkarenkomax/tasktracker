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
    Department,
    MemberDeputy,
    Organization,
    OrganizationMember,
    OrgPosition,
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

    async def count(self) -> int:
        statement = select(func.count()).select_from(Organization)
        return await count(self._session, statement)

    async def list_all(self) -> list[Organization]:
        """Every organization on the installation.

        Only the portal administrator's callers reach this: an ordinary member
        reads through ``list_for_user`` and stays inside their own tenant.
        """
        return await fetch_all(self._session, select(Organization).order_by(Organization.name))

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

    async def list_members(
        self, organization_id: UUID
    ) -> list[tuple[OrganizationMember, User, OrgPosition | None]]:
        """Everyone in the organization, with the position they hold (stage 2.5).

        The position title travels with the member because every place that
        offers a list of people needs to say *who this is* - a picker that shows
        thirty rows of similar names is a picker nobody can choose from. The join
        is an outer one: most members hold no position, and an inner join would
        quietly drop them out of the roster.
        """
        statement = (
            select(OrganizationMember, User, OrgPosition)
            .join(User, User.id == OrganizationMember.user_id)
            .outerjoin(OrgPosition, OrgPosition.id == OrganizationMember.position_id)
            .where(OrganizationMember.organization_id == organization_id)
            .order_by(User.username)
        )
        rows: list[tuple[Any, ...]] = await fetch_pairs(self._session, statement)
        return [(row[0], row[1], row[2]) for row in rows]

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

    async def is_member(self, organization_id: UUID, user_id: UUID) -> bool:
        """Is this person in this organization?

        The chart references people by id, and a reference to somebody outside the
        tenant would draw a node no page can resolve. Every writer checks this
        rather than trusting the client.
        """
        statement = (
            select(func.count())
            .select_from(OrganizationMember)
            .where(
                OrganizationMember.organization_id == organization_id,
                OrganizationMember.user_id == user_id,
            )
        )
        return await count(self._session, statement) > 0


class DepartmentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, department_id: UUID, *, organization_id: UUID) -> Department | None:
        return await fetch_one(
            self._session,
            select(Department).where(
                Department.id == department_id,
                Department.organization_id == organization_id,
            ),
        )

    async def list_all(self, organization_id: UUID) -> list[Department]:
        # Ordered by the stored position rather than the name: the order somebody
        # arranged is the order they want to read.
        return await fetch_all(
            self._session,
            select(Department)
            .where(Department.organization_id == organization_id)
            .order_by(Department.position, Department.name),
        )

    async def name_taken(
        self, organization_id: UUID, name: str, *, exclude_id: UUID | None = None
    ) -> bool:
        existing = await fetch_one(
            self._session,
            select(Department).where(
                Department.organization_id == organization_id,
                Department.name == name,
            ),
        )
        return existing is not None and existing.id != exclude_id

    async def add(self, department: Department) -> Department:
        self._session.add(department)
        await self._session.flush()
        return department

    async def delete(self, department: Department) -> None:
        await self._session.delete(department)
        await self._session.flush()

    async def next_position(self, organization_id: UUID, parent_id: UUID | None) -> int:
        """Where the next sibling goes.

        One past the last one rather than the count: deleting a department in the
        middle must not make the next insert collide with the name of an existing
        sibling.
        """
        conditions = [
            Department.organization_id == organization_id,
            Department.parent_id.is_(None)
            if parent_id is None
            else Department.parent_id == parent_id,
        ]
        statement = select(func.max(Department.position)).where(*conditions)
        current = await self._session.scalar(statement)
        return 0 if current is None else int(current) + 1


class PositionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, position_id: UUID, *, organization_id: UUID) -> OrgPosition | None:
        return await fetch_one(
            self._session,
            select(OrgPosition).where(
                OrgPosition.id == position_id,
                OrgPosition.organization_id == organization_id,
            ),
        )

    async def list_all(self, organization_id: UUID) -> list[OrgPosition]:
        # A null rank sorts last in PostgreSQL by default, which is what we want:
        # an unranked title never outranks one somebody ranked on purpose.
        return await fetch_all(
            self._session,
            select(OrgPosition)
            .where(OrgPosition.organization_id == organization_id)
            .order_by(OrgPosition.rank.desc().nullslast(), OrgPosition.title),
        )

    async def title_taken(
        self, organization_id: UUID, title: str, *, exclude_id: UUID | None = None
    ) -> bool:
        existing = await fetch_one(
            self._session,
            select(OrgPosition).where(
                OrgPosition.organization_id == organization_id,
                OrgPosition.title == title,
            ),
        )
        return existing is not None and existing.id != exclude_id

    async def add(self, position: OrgPosition) -> OrgPosition:
        self._session.add(position)
        await self._session.flush()
        return position

    async def delete(self, position: OrgPosition) -> None:
        await self._session.delete(position)
        await self._session.flush()


class DeputyRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_all(self, organization_id: UUID) -> list[tuple[UUID, list[UUID]]]:
        """Every deputy row in this organization, grouped by the person covered.

        Grouped here rather than in the service because the grouping needs the
        whole table; doing it per member would mean one query per member inside a
        single request.
        """
        statement = (
            select(MemberDeputy.user_id, MemberDeputy.deputy_id)
            .where(MemberDeputy.organization_id == organization_id)
            .order_by(MemberDeputy.user_id, MemberDeputy.deputy_id)
        )
        rows = await self._session.execute(statement)
        grouped: dict[UUID, list[UUID]] = {}
        for user_id, deputy_id in rows:
            grouped.setdefault(user_id, []).append(deputy_id)
        return list(grouped.items())

    async def list_for(self, organization_id: UUID, user_id: UUID) -> list[UUID]:
        """Deputies of one person.

        Returns bare ids: the reader already has the member list and joining the
        two here would return the same rows twice for every deputy.
        """
        statement = select(MemberDeputy.deputy_id).where(
            MemberDeputy.organization_id == organization_id,
            MemberDeputy.user_id == user_id,
        )
        rows = await self._session.scalars(statement)
        return [row for row in rows]

    async def add(
        self, *, organization_id: UUID, user_id: UUID, deputy_id: UUID
    ) -> MemberDeputy | None:
        existing = await fetch_one(
            self._session,
            select(MemberDeputy).where(
                MemberDeputy.organization_id == organization_id,
                MemberDeputy.user_id == user_id,
                MemberDeputy.deputy_id == deputy_id,
            ),
        )
        if existing is not None:
            return existing
        row = MemberDeputy(organization_id=organization_id, user_id=user_id, deputy_id=deputy_id)
        self._session.add(row)
        await self._session.flush()
        return row

    async def remove(self, *, organization_id: UUID, user_id: UUID, deputy_id: UUID) -> bool:
        row = await fetch_one(
            self._session,
            select(MemberDeputy).where(
                MemberDeputy.organization_id == organization_id,
                MemberDeputy.user_id == user_id,
                MemberDeputy.deputy_id == deputy_id,
            ),
        )
        if row is None:
            return False
        await self._session.delete(row)
        await self._session.flush()
        return True


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
