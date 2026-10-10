"""One list of people for the merged "Employees" screen (stage 2.17).

This used to be two screens and two lists: the organization's members, and the
portal directory of every account on the installation. They answered different
questions ("who works with us" and "who is registered here at all"), but a person
looking for a colleague had to know which one to open, and the two answers
disagreed about the same human - the directory had no role, the roster had no
"not in this organization" row. One table, with a column that says which is
which, is the honest shape for that.

Two decisions worth stating, because they are the ones a reader might otherwise
take for a bug:

**The extra rows are the installation's, not the organization's.** An account
that does not belong to this organization is somebody else's business - another
tenant's colleague, or an account registered and never invited. A superuser may
see them because a superuser administers the deployment; an ordinary member may
not, and asking for them is a permission error rather than an empty page. The
reason for the rule is the same as everywhere else in Core: the organization is
the boundary, and a directory that quietly crosses it is a leak with a filter.

**Sorting and filtering happen here, not in the browser.** The directory is
paginated - a portal with a few thousand accounts must not ship all of them to
every member who opens a screen - and a table that sorted one page of fifty rows
in the browser would show an order that contradicts itself on the next page. The
alternative (two lists, merged and sorted in the client) has the same defect
twice over, and additionally needs two pagination cursors to stay in step.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.core.organizations.models import Department, OrganizationMember, OrgPosition
from app.core.permissions.roles import ROLE_RANK
from app.core.users.models import User, UserStatus
from app.database.helpers import count, fetch_pairs

#: Most privileged first: the order roles are handed out in, and the order a
#: reader expects to see them in - which is the rank, not the spelling.
ROLE_ORDER = sorted(ROLE_RANK, key=lambda role: -ROLE_RANK[role])

#: The sort keys the screen offers, as columns. Each is a column name rather
#: than a raw expression so that the mapping from "what the header says" to
#: "what SQL runs" is one dict in one place; a request naming anything else is
#: refused by the router, not passed through as a column name.
SORT_COLUMNS: dict[str, InstrumentedAttribute[Any]] = {
    "name": User.username,
    "email": User.email,
    "role": OrganizationMember.role,
    "department": Department.name,
    "position": OrgPosition.title,
    "status": User.status,
    "created_at": User.created_at,
    "last_login_at": User.last_login_at,
    # Presence (stage 2.9). Sortable next to the login time because they disagree:
    # "who was here this morning" is the question a roster is asked, and sorting
    # by sign-in time answers a different one.
    "last_seen": User.last_seen,
}


@dataclass(frozen=True, slots=True)
class PeopleQuery:
    """What the screen asked for, already validated by the router."""

    search: str | None
    role: str | None
    department_id: UUID | None
    position_id: UUID | None
    status: str | None
    #: "members" (the default), "outside" (accounts not in this organization,
    #: superusers only) or "all".
    scope: str
    sort: str
    direction: str
    limit: int
    offset: int


@dataclass(frozen=True, slots=True)
class PersonRow:
    """One row: the account, and where it sits in this organization."""

    user: User
    membership: OrganizationMember | None
    department: Department | None
    position: OrgPosition | None


@dataclass(frozen=True, slots=True)
class PeoplePage:
    rows: list[PersonRow]
    total: int


class PeopleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def page(self, organization_id: UUID, query: PeopleQuery) -> PeoplePage:
        statement = self._statement(organization_id, query)
        statement = statement.order_by(*self._order(query))
        rows = await fetch_pairs(
            self._session,
            statement.limit(query.limit).offset(query.offset),
        )
        return PeoplePage(
            rows=[
                PersonRow(user=row[0], membership=row[1], department=row[2], position=row[3])
                for row in rows
            ],
            total=await self._total(organization_id, query),
        )

    def _statement(
        self, organization_id: UUID, query: PeopleQuery
    ) -> Select[tuple[User, OrganizationMember, Department, OrgPosition]]:
        # Left joins from `users`: the non-member rows the superuser asked for
        # have no membership, no department and no position, and an inner join
        # would throw exactly those rows away.
        statement: Select[tuple[User, OrganizationMember, Department, OrgPosition]] = (
            select(User, OrganizationMember, Department, OrgPosition)
            .outerjoin(
                OrganizationMember,
                and_(
                    OrganizationMember.user_id == User.id,
                    OrganizationMember.organization_id == organization_id,
                ),
            )
            .outerjoin(Department, Department.id == OrganizationMember.department_id)
            .outerjoin(OrgPosition, OrgPosition.id == OrganizationMember.position_id)
        )

        if query.scope == "members":
            statement = statement.where(OrganizationMember.user_id.is_not(None))
        elif query.scope == "outside":
            statement = statement.where(OrganizationMember.user_id.is_(None))

        if query.search:
            needle = f"%{query.search.strip()}%"
            statement = statement.where(
                or_(
                    User.username.ilike(needle),
                    User.email.ilike(needle),
                    User.first_name.ilike(needle),
                    User.last_name.ilike(needle),
                    OrgPosition.title.ilike(needle),
                    Department.name.ilike(needle),
                )
            )
        if query.role:
            # Comparing the string the screen holds rather than casting it to the
            # enum: a filter for a role that does not exist has to return nothing,
            # and a cast would raise instead.
            statement = statement.where(OrganizationMember.role == query.role)
        if query.department_id:
            statement = statement.where(OrganizationMember.department_id == query.department_id)
        if query.position_id:
            statement = statement.where(OrganizationMember.position_id == query.position_id)
        if query.status:
            statement = statement.where(User.status == UserStatus(query.status))
        return statement

    async def _total(self, organization_id: UUID, query: PeopleQuery) -> int:
        # Counted from the same statement rather than from a second, simpler
        # query: the two would drift the moment a filter touched a joined table,
        # and the symptom is a "showing 1-50 of 178" line that is simply wrong.
        counted = (
            self._statement(organization_id, query).order_by(None).with_only_columns(func.count())
        )
        return await count(self._session, counted)

    def _order(self, query: PeopleQuery) -> list[Any]:
        if query.sort == "role":
            # By rank, not by name. Alphabetically "admin" would come first and
            # the owner - the person a reader is usually looking for - last,
            # which is an order nobody asked for in either direction.
            column: Any = case(
                {role: rank for rank, role in enumerate(ROLE_ORDER)},
                value=OrganizationMember.role,
                else_=len(ROLE_ORDER),
            )
        else:
            column = SORT_COLUMNS[query.sort]
        # `nulls_last` because a missing placement sorting above a real one is
        # not an order anybody asked for, whichever way the arrow points.
        direction = column.desc() if query.direction == "desc" else column.asc()
        return [direction.nulls_last()]
