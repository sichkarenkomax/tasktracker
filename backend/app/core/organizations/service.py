"""Organization, membership and team services.

This is the public interface other modules are allowed to call. Nothing outside
Core may write to these tables directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.core.errors import ConflictError, NotFoundError, ValidationError
from app.core.events.names import (
    ORG_DEPARTMENT_CREATED,
    ORG_DEPARTMENT_DELETED,
    ORG_DEPARTMENT_UPDATED,
    ORG_DEPUTY_ADDED,
    ORG_DEPUTY_REMOVED,
    ORG_MEMBER_PLACED,
    ORG_POSITION_CREATED,
    ORG_POSITION_DELETED,
    ORG_POSITION_UPDATED,
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
from app.core.organizations.models import (
    Department,
    Organization,
    OrganizationMember,
    OrgPosition,
    Team,
)
from app.core.organizations.repository import (
    DepartmentRepository,
    DeputyRepository,
    OrganizationRepository,
    PositionRepository,
    TeamRepository,
)
from app.core.permissions.roles import OrganizationRole
from app.core.users.models import User
from app.core.users.repository import UserRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


@dataclass(frozen=True, slots=True)
class OrgStructureSnapshot:
    """The whole chart in one object.

    Returned rather than assembled in the router so the rule about what a valid
    structure is lives in one place, and so a future cache can key on the
    organization id alone.
    """

    departments: list[Department]
    positions: list[OrgPosition]
    members: list[tuple[OrganizationMember, User]]
    #: user id -> the ids of the people who cover for them.
    deputies: dict[UUID, list[UUID]] = dataclass_field(default_factory=dict)


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


class OrgStructureService:
    """Departments, positions, reporting lines and deputies.

    Everything that draws the org chart writes through here. Two invariants are
    enforced in this class rather than in the database, because the database can
    express neither of them on its own:

    * a department tree is acyclic - ``A -> B -> A`` satisfies every foreign key
      and would hang any reader that walks it;
    * a reporting tree is acyclic for the same reason, with the extra rule that a
      person is not their own manager.

    Both are checked by walking the chain to the root before writing, so the cost
    is one query per ancestor and the answer is exact rather than a heuristic.
    """

    #: Long enough that no real organization chain trips it, short enough that a
    #: cycle introduced by hand cannot spin here. Reaching it means the tree is
    #: already broken, so refusing is the right answer.
    MAX_DEPTH: Final = 64

    def __init__(
        self,
        departments: DepartmentRepository,
        positions: PositionRepository,
        deputies: DeputyRepository,
        members: OrganizationRepository,
        bus: EventBus,
    ) -> None:
        self._departments = departments
        self._positions = positions
        self._deputies = deputies
        self._members = members
        self._bus = bus

    # --- departments -------------------------------------------------------

    async def create_department(
        self,
        *,
        organization_id: UUID,
        actor: User,
        name: str,
        parent_id: UUID | None = None,
        description: str | None = None,
    ) -> Department:
        # Checked here rather than left to the unique index: a raw IntegrityError
        # would surface as a 500, and "that name is taken" is a conflict the caller
        # can act on. The index stays as the guarantee that two simultaneous
        # requests cannot both win.
        if await self._departments.name_taken(organization_id, name.strip()):
            raise ConflictError(
                f"A department named '{name.strip()}' already exists in this organization"
            )

        if parent_id is not None:
            parent = await self._departments.get(parent_id, organization_id=organization_id)
            if parent is None:
                raise NotFoundError("Parent department not found")

        department = await self._departments.add(
            Department(
                organization_id=organization_id,
                name=name.strip(),
                description=description,
                parent_id=parent_id,
                position=await self._departments.next_position(organization_id, parent_id),
            )
        )
        await self._bus.publish_event(
            ORG_DEPARTMENT_CREATED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "department_id": str(department.id),
                "summary": f"created department {department.name!r}",
            },
        )
        return department

    async def update_department(
        self,
        department: Department,
        *,
        actor: User,
        name: str | None = None,
        description: str | None = None,
        parent_id: UUID | None = None,
        parent_set: bool = False,
        head_id: UUID | None = None,
        head_set: bool = False,
    ) -> Department:
        organization_id = department.organization_id
        changed: list[str] = []

        if name is not None and name.strip() and name.strip() != department.name:
            department.name = name.strip()
            changed.append("name")

        if description is not None and description != department.description:
            department.description = description
            changed.append("description")

        if parent_set:
            if parent_id == department.id:
                raise ValidationError(
                    "A department cannot be its own parent",
                    details={"field": "parent_id"},
                )
            if parent_id is not None:
                parent = await self._departments.get(parent_id, organization_id=organization_id)
                if parent is None:
                    raise NotFoundError("Parent department not found")
                if await self._is_department_descendant(organization_id, parent.id, department.id):
                    raise ValidationError(
                        "That parent sits below this department, which would make a loop",
                        details={"field": "parent_id"},
                    )
            if parent_id != department.parent_id:
                department.parent_id = parent_id
                changed.append("parent")

        if head_set:
            if head_id is not None and not await self._members.is_member(organization_id, head_id):
                raise ValidationError(
                    "Department head must be a member of the organization",
                    details={"field": "head_id"},
                )
            if head_id != department.head_id:
                department.head_id = head_id
                changed.append("head")

        if changed:
            await self._bus.publish_event(
                ORG_DEPARTMENT_UPDATED,
                actor_id=actor.id,
                payload={
                    "organization_id": str(organization_id),
                    "department_id": str(department.id),
                    "changes": changed,
                    "summary": f"updated department {department.name!r}",
                },
            )
        return department

    async def delete_department(self, department: Department, *, actor: User) -> None:
        """Remove a department, leaving the people in it unplaced.

        Members and child departments are detached rather than deleted. A person's
        employment and the neighbouring units are facts that outlive this
        spreadsheet-like object, and silently taking a department with it would
        destroy data nobody asked to destroy.
        """
        organization_id = department.organization_id
        for child in await self._departments.list_all(organization_id):
            if child.parent_id == department.id:
                child.parent_id = department.parent_id
        for member in await self._members.list_members(organization_id):
            if member[0].department_id == department.id:
                member[0].department_id = None

        await self._departments.delete(department)
        await self._bus.publish_event(
            ORG_DEPARTMENT_DELETED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "department_id": str(department.id),
                "summary": "deleted a department",
            },
        )

    async def _is_department_descendant(
        self, organization_id: UUID, candidate_id: UUID, ancestor_id: UUID
    ) -> bool:
        """Is `candidate` somewhere below `ancestor`?

        Walks up from the candidate. Bounded so that a tree already containing a
        loop - imported from a spreadsheet, say - ends the walk instead of hanging
        the request.
        """
        current = candidate_id
        for _ in range(self.MAX_DEPTH):
            if current == ancestor_id:
                return True
            row = await self._departments.get(current, organization_id=organization_id)
            if row is None or row.parent_id is None:
                return False
            current = row.parent_id
        return False

    # --- positions ---------------------------------------------------------

    async def create_position(
        self,
        *,
        organization_id: UUID,
        actor: User,
        title: str,
        department_id: UUID | None = None,
        description: str | None = None,
        rank: int | None = None,
    ) -> OrgPosition:
        # As with departments: a duplicate title is a conflict, not a crash.
        if await self._positions.title_taken(organization_id, title.strip()):
            raise ConflictError(
                f"A position titled '{title.strip()}' already exists in this organization"
            )

        if department_id is not None:
            department = await self._departments.get(department_id, organization_id=organization_id)
            if department is None:
                raise NotFoundError("Department not found")

        position = await self._positions.add(
            OrgPosition(
                organization_id=organization_id,
                title=title.strip(),
                department_id=department_id,
                description=description,
                rank=rank,
            )
        )
        await self._bus.publish_event(
            ORG_POSITION_CREATED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "position_id": str(position.id),
                "summary": f"created position {position.title!r}",
            },
        )
        return position

    async def update_position(
        self,
        position: OrgPosition,
        *,
        actor: User,
        title: str | None = None,
        department_id: UUID | None = None,
        department_set: bool = False,
        description: str | None = None,
        rank: int | None = None,
        rank_set: bool = False,
    ) -> OrgPosition:
        organization_id = position.organization_id
        changed: list[str] = []

        if title is not None and title.strip() and title.strip() != position.title:
            position.title = title.strip()
            changed.append("title")

        if description is not None and description != position.description:
            position.description = description
            changed.append("description")

        if department_set:
            if department_id is not None:
                department = await self._departments.get(
                    department_id, organization_id=organization_id
                )
                if department is None:
                    raise NotFoundError("Department not found")
            if department_id != position.department_id:
                position.department_id = department_id
                changed.append("department")

        if rank_set and rank != position.rank:
            position.rank = rank
            changed.append("rank")

        if changed:
            await self._bus.publish_event(
                ORG_POSITION_UPDATED,
                actor_id=actor.id,
                payload={
                    "organization_id": str(organization_id),
                    "position_id": str(position.id),
                    "changes": changed,
                    "summary": f"updated position {position.title!r}",
                },
            )
        return position

    async def delete_position(self, position: OrgPosition, *, actor: User) -> None:
        organization_id = position.organization_id
        for member, _ in await self._members.list_members(organization_id):
            if member.position_id == position.id:
                member.position_id = None

        await self._positions.delete(position)
        await self._bus.publish_event(
            ORG_POSITION_DELETED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "position_id": str(position.id),
                "summary": "deleted a position",
            },
        )

    # --- where a person sits ------------------------------------------------

    async def place_member(
        self,
        member: OrganizationMember,
        *,
        actor: User,
        department_id: UUID | None = None,
        department_set: bool = False,
        position_id: UUID | None = None,
        position_set: bool = False,
        manager_id: UUID | None = None,
        manager_set: bool = False,
    ) -> OrganizationMember:
        organization_id = member.organization_id
        changed: list[str] = []

        if department_set and department_id != member.department_id:
            if department_id is not None:
                department = await self._departments.get(
                    department_id, organization_id=organization_id
                )
                if department is None:
                    raise NotFoundError("Department not found")
            member.department_id = department_id
            changed.append("department")

        if position_set and position_id != member.position_id:
            if position_id is not None:
                position = await self._positions.get(position_id, organization_id=organization_id)
                if position is None:
                    raise NotFoundError("Position not found")
            member.position_id = position_id
            changed.append("position")

        if manager_set and manager_id != member.manager_id:
            if manager_id is not None:
                if manager_id == member.user_id:
                    raise ValidationError(
                        "A person cannot be their own manager",
                        details={"field": "manager_id"},
                    )
                if not await self._members.is_member(organization_id, manager_id):
                    raise ValidationError(
                        "A manager must be a member of the organization",
                        details={"field": "manager_id"},
                    )
                if await self._reports_to(organization_id, member.user_id, manager_id):
                    raise ValidationError(
                        "That person already reports to this one, directly or not",
                        details={"field": "manager_id"},
                    )
            member.manager_id = manager_id
            changed.append("manager")

        if changed:
            await self._bus.publish_event(
                ORG_MEMBER_PLACED,
                actor_id=actor.id,
                payload={
                    "organization_id": str(organization_id),
                    "user_id": str(member.user_id),
                    "changes": changed,
                    "summary": "updated somebody's place in the structure",
                },
            )
        return member

    async def _reports_to(
        self, organization_id: UUID, user_id: UUID, candidate_manager_id: UUID
    ) -> bool:
        """Would `candidate_manager_id` end up below `user_id`?

        Walks up from the proposed manager. If the chain reaches `user_id`, the
        move would close a loop.

        Scoped to this organization on purpose. Looking the chain up by user id
        alone would find *some* membership of that person - and a person can be a
        member of several organizations - so the walk could follow a line from a
        different tenant and answer about a structure this one knows nothing
        about.
        """
        current = candidate_manager_id
        for _ in range(self.MAX_DEPTH):
            if current == user_id:
                return True
            member = await self._members.get_member(
                organization_id=organization_id, user_id=current
            )
            if member is None or member.manager_id is None:
                return False
            current = member.manager_id
        return False

    # --- deputies -----------------------------------------------------------

    async def add_deputy(
        self, *, organization_id: UUID, actor: User, user_id: UUID, deputy_id: UUID
    ) -> None:
        if user_id == deputy_id:
            raise ValidationError(
                "Somebody cannot be their own deputy", details={"field": "deputy_id"}
            )
        for candidate in (user_id, deputy_id):
            if not await self._members.is_member(organization_id, candidate):
                raise ValidationError(
                    "Both people must be members of the organization",
                    details={"field": "user_id"},
                )
        await self._deputies.add(
            organization_id=organization_id, user_id=user_id, deputy_id=deputy_id
        )
        await self._bus.publish_event(
            ORG_DEPUTY_ADDED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "deputy_id": str(deputy_id),
                "summary": "added a deputy",
            },
        )

    async def remove_deputy(
        self, *, organization_id: UUID, actor: User, user_id: UUID, deputy_id: UUID
    ) -> None:
        if not await self._deputies.remove(
            organization_id=organization_id, user_id=user_id, deputy_id=deputy_id
        ):
            raise NotFoundError("That deputy is not recorded")
        await self._bus.publish_event(
            ORG_DEPUTY_REMOVED,
            actor_id=actor.id,
            payload={
                "organization_id": str(organization_id),
                "user_id": str(user_id),
                "deputy_id": str(deputy_id),
                "summary": "removed a deputy",
            },
        )

    # --- the whole picture --------------------------------------------------

    async def snapshot(self, organization_id: UUID) -> OrgStructureSnapshot:
        """Everything the chart needs, in one round trip.

        The editor would otherwise issue one request per node to discover the
        shape, which on a real organization is a hundred requests before the
        first pixel. One read, one consistent view.
        """
        departments = await self._departments.list_all(organization_id)
        positions = await self._positions.list_all(organization_id)
        roster = await self._members.list_members(organization_id)

        # One query for every deputy's row rather than one per member: on a real
        # organization the per-member version is a hundred sequential round trips
        # inside a single HTTP request, and the difference is the difference
        # between the chart opening and appearing to hang.
        deputies: dict[UUID, list[UUID]] = {}
        for user_id, deputy_ids in await self._deputies.list_all(organization_id):
            deputies.setdefault(user_id, []).extend(deputy_ids)

        return OrgStructureSnapshot(
            departments=departments,
            positions=positions,
            members=roster,
            deputies=deputies,
        )
