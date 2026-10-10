"""Organization, membership and team API."""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, status

from app.config.settings import get_settings
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.dependencies import EventBusDep
from app.core.errors import ConflictError, NotFoundError, PermissionDeniedError
from app.core.organizations.repository import (
    DepartmentRepository,
    DeputyRepository,
    OrganizationRepository,
    PositionRepository,
    TeamRepository,
)
from app.core.organizations.schemas import (
    DepartmentCreate,
    DepartmentRead,
    DepartmentUpdate,
    DeputyAdd,
    MemberAdd,
    MemberPlacementUpdate,
    MemberRoleUpdate,
    MembershipRead,
    OrganizationCreate,
    OrganizationRead,
    OrganizationUpdate,
    OrgStructureRead,
    PlacementRead,
    PositionCreate,
    PositionRead,
    PositionUpdate,
    TeamCreate,
    TeamMemberAdd,
    TeamRead,
    TeamUpdate,
    UserSummaryRead,
)
from app.core.organizations.service import OrganizationService, OrgStructureService, TeamService
from app.core.permissions.dependencies import require_permission
from app.core.permissions.service import AuthorizationService
from app.core.users.models import User
from app.core.users.repository import UserRepository

router = APIRouter(tags=["organizations"])


async def _organizations(session: SessionDep, bus: EventBusDep) -> OrganizationService:
    return OrganizationService(OrganizationRepository(session), UserRepository(session), bus)


# --- organizations ------------------------------------------------------
@router.post(
    "/organizations",
    response_model=OrganizationRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create organization (caller becomes owner)",
)
async def create_organization(
    payload: OrganizationCreate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> OrganizationRead:
    repository = OrganizationRepository(session)
    if get_settings().single_organization:
        # On a single-organization installation the organization is a piece of
        # portal configuration, not something a tenant signs itself up for.
        # The permission guard runs first so that a refusal never discloses
        # whether the one organization already exists.
        if not user.is_superuser:
            raise PermissionDeniedError("Only a portal administrator can set up the organization")
        if await repository.count() > 0:
            raise ConflictError("This installation runs a single organization")

    service = await _organizations(session, bus)
    organization = await service.create(
        owner=user,
        name=payload.name,
        slug=payload.resolved_slug(),
        description=payload.description,
    )
    await session.commit()
    return OrganizationRead.model_validate(organization)


@router.get("/organizations", response_model=list[OrganizationRead], summary="My organizations")
async def list_organizations(user: CurrentUser, session: SessionDep) -> list[OrganizationRead]:
    repository = OrganizationRepository(session)
    if user.is_superuser:
        organizations = await repository.list_all()
        return [OrganizationRead.model_validate(organization) for organization in organizations]
    rows = await repository.list_for_user(user.id)
    return [OrganizationRead.model_validate(organization) for organization, _ in rows]


@router.get(
    "/organizations/{organization_id}",
    response_model=OrganizationRead,
    summary="Organization details",
)
async def read_organization(
    organization_id: UUID,
    user: Annotated[User, Depends(require_permission("organization.view"))],
    session: SessionDep,
) -> OrganizationRead:
    organization = await OrganizationRepository(session).get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")
    return OrganizationRead.model_validate(organization)


@router.patch(
    "/organizations/{organization_id}",
    response_model=OrganizationRead,
    summary="Update organization",
)
async def update_organization(
    organization_id: UUID,
    payload: OrganizationUpdate,
    user: Annotated[User, Depends(require_permission("organization.update"))],
    session: SessionDep,
    bus: EventBusDep,
) -> OrganizationRead:
    repository = OrganizationRepository(session)
    organization = await repository.get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")

    service = await _organizations(session, bus)
    updated = await service.update(
        organization,
        actor=user,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    return OrganizationRead.model_validate(updated)


@router.delete(
    "/organizations/{organization_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete organization",
)
async def delete_organization(
    organization_id: UUID,
    user: Annotated[User, Depends(require_permission("organization.delete"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = OrganizationRepository(session)
    organization = await repository.get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")

    service = await _organizations(session, bus)
    await service.delete(organization, actor=user)
    await session.commit()


# --- membership ---------------------------------------------------------
@router.get(
    "/organizations/{organization_id}/members",
    response_model=list[MembershipRead],
    summary="List organization members",
)
async def list_members(
    organization_id: UUID,
    user: Annotated[User, Depends(require_permission("organization.view"))],
    session: SessionDep,
) -> list[MembershipRead]:
    rows = await OrganizationRepository(session).list_members(organization_id)
    return [
        MembershipRead(
            user_id=member.user_id,
            role=member.role,
            joined_at=member.joined_at,
            user=UserSummaryRead.model_validate(account),
            # The title, not the id: the picker writes it under the name (2.5), and
            # a client that had to resolve ids into titles would do it once per
            # row, in the browser.
            position_title=position.title if position is not None else None,
        )
        for member, account, position in rows
    ]


@router.post(
    "/organizations/{organization_id}/members",
    response_model=MembershipRead,
    status_code=status.HTTP_201_CREATED,
    summary="Add member by user id or email",
)
async def add_member(
    organization_id: UUID,
    payload: MemberAdd,
    user: Annotated[User, Depends(require_permission("organization.members.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> MembershipRead:
    repository = OrganizationRepository(session)
    organization = await repository.get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")

    service = await _organizations(session, bus)
    member = await service.add_member(
        organization=organization,
        actor=user,
        role=payload.role,
        user_id=payload.user_id,
        email=payload.email,
    )
    await session.commit()
    return MembershipRead(user_id=member.user_id, role=member.role, joined_at=member.joined_at)


@router.patch(
    "/organizations/{organization_id}/members/{user_id}",
    response_model=MembershipRead,
    summary="Change member role",
)
async def change_member_role(
    organization_id: UUID,
    user_id: UUID,
    payload: MemberRoleUpdate,
    user: Annotated[User, Depends(require_permission("organization.members.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> MembershipRead:
    repository = OrganizationRepository(session)
    organization = await repository.get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")

    member = await repository.get_member(organization_id=organization_id, user_id=user_id)
    if member is None:
        raise NotFoundError("This user is not a member of the organization")

    # Rank check: a role may only touch strictly lower-ranked members.
    await AuthorizationService(session).require_manage_member(
        user=user,
        organization_id=organization_id,
        target_user_id=member.user_id,
        target_role=member.role,
        new_role=payload.role,
    )
    service = await _organizations(session, bus)
    updated = await service.change_member_role(
        organization=organization, member=member, new_role=payload.role, actor=user
    )
    await session.commit()
    return MembershipRead(user_id=updated.user_id, role=updated.role, joined_at=updated.joined_at)


@router.delete(
    "/organizations/{organization_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove member",
)
async def remove_member(
    organization_id: UUID,
    user_id: UUID,
    user: Annotated[User, Depends(require_permission("organization.members.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = OrganizationRepository(session)
    organization = await repository.get(organization_id)
    if organization is None:
        raise NotFoundError("Organization not found")

    member = await repository.get_member(organization_id=organization_id, user_id=user_id)
    if member is None:
        raise NotFoundError("This user is not a member of the organization")

    await AuthorizationService(session).require_manage_member(
        user=user,
        organization_id=organization_id,
        target_user_id=member.user_id,
        target_role=member.role,
    )
    service = await _organizations(session, bus)
    await service.remove_member(organization=organization, member=member, actor=user)
    await session.commit()


# --- teams --------------------------------------------------------------
@router.post(
    "/organizations/{organization_id}/teams",
    response_model=TeamRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create team",
)
async def create_team(
    organization_id: UUID,
    payload: TeamCreate,
    user: CurrentUser,
    _guard: Annotated[User, Depends(require_permission("team.create"))],
    session: SessionDep,
    bus: EventBusDep,
) -> TeamRead:
    team = await TeamService(TeamRepository(session), bus).create(
        organization_id=organization_id,
        actor=user,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    return TeamRead.model_validate(team)


@router.get(
    "/organizations/{organization_id}/teams",
    response_model=list[TeamRead],
    summary="List teams",
)
async def list_teams(
    organization_id: UUID,
    user: Annotated[User, Depends(require_permission("team.view"))],
    session: SessionDep,
) -> list[TeamRead]:
    repository = TeamRepository(session)
    result: list[TeamRead] = []
    for team in await repository.list_for_organization(organization_id):
        read = TeamRead.model_validate(team)
        read.member_ids = await repository.list_member_ids(team.id)
        result.append(read)
    return result


@router.get(
    "/organizations/{organization_id}/teams/{team_id}",
    response_model=TeamRead,
    summary="Team details",
)
async def read_team(
    organization_id: UUID,
    team_id: UUID,
    user: Annotated[User, Depends(require_permission("team.view"))],
    session: SessionDep,
) -> TeamRead:
    repository = TeamRepository(session)
    team = await repository.get(team_id, organization_id=organization_id)
    if team is None:
        raise NotFoundError("Team not found")
    read = TeamRead.model_validate(team)
    read.member_ids = await repository.list_member_ids(team.id)
    return read


@router.patch(
    "/organizations/{organization_id}/teams/{team_id}",
    response_model=TeamRead,
    summary="Update team",
)
async def update_team(
    organization_id: UUID,
    team_id: UUID,
    payload: TeamUpdate,
    user: CurrentUser,
    _guard: Annotated[User, Depends(require_permission("team.update"))],
    session: SessionDep,
    bus: EventBusDep,
) -> TeamRead:
    repository = TeamRepository(session)
    team = await repository.get(team_id, organization_id=organization_id)
    if team is None:
        raise NotFoundError("Team not found")

    updated = await TeamService(repository, bus).update(
        team, actor=user, name=payload.name, description=payload.description
    )
    await session.commit()
    return TeamRead.model_validate(updated)


@router.delete(
    "/organizations/{organization_id}/teams/{team_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete team",
)
async def delete_team(
    organization_id: UUID,
    team_id: UUID,
    user: CurrentUser,
    _guard: Annotated[User, Depends(require_permission("team.delete"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = TeamRepository(session)
    team = await repository.get(team_id, organization_id=organization_id)
    if team is None:
        raise NotFoundError("Team not found")

    await TeamService(repository, bus).delete(team, actor=user)
    await session.commit()


@router.post(
    "/organizations/{organization_id}/teams/{team_id}/members",
    status_code=status.HTTP_201_CREATED,
    summary="Add team member",
)
async def add_team_member(
    organization_id: UUID,
    team_id: UUID,
    payload: TeamMemberAdd,
    user: CurrentUser,
    _guard: Annotated[User, Depends(require_permission("team.members.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> dict[str, str]:
    repository = TeamRepository(session)
    team = await repository.get(team_id, organization_id=organization_id)
    if team is None:
        raise NotFoundError("Team not found")

    await TeamService(repository, bus).add_member(team, actor=user, user_id=payload.user_id)
    await session.commit()
    return {"status": "added"}


@router.delete(
    "/organizations/{organization_id}/teams/{team_id}/members/{user_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove team member",
)
async def remove_team_member(
    organization_id: UUID,
    team_id: UUID,
    user_id: UUID,
    user: CurrentUser,
    _guard: Annotated[User, Depends(require_permission("team.members.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = TeamRepository(session)
    team = await repository.get(team_id, organization_id=organization_id)
    if team is None:
        raise NotFoundError("Team not found")

    await TeamService(repository, bus).remove_member(team, actor=user, user_id=user_id)
    await session.commit()


# ---------------------------------------------------------------------------
# Organization structure
# ---------------------------------------------------------------------------


async def _org_structure(session: SessionDep, bus: EventBusDep) -> OrgStructureService:
    return OrgStructureService(
        DepartmentRepository(session),
        PositionRepository(session),
        DeputyRepository(session),
        OrganizationRepository(session),
        bus,
    )


@router.get(
    "/organizations/{organization_id}/structure",
    response_model=OrgStructureRead,
    summary="Departments, positions, reporting lines and deputies",
)
async def read_structure(
    organization_id: UUID,
    user: Annotated[User, Depends(require_permission("orgstructure.view"))],
    session: SessionDep,
    bus: EventBusDep,
) -> OrgStructureRead:
    snapshot = await (await _org_structure(session, bus)).snapshot(organization_id)
    placements = {
        member.user_id: PlacementRead(
            user_id=member.user_id,
            department_id=member.department_id,
            position_id=member.position_id,
            manager_id=member.manager_id,
            deputies=snapshot.deputies.get(member.user_id, []),
        )
        for member, _, _ in snapshot.members
    }
    return OrgStructureRead(
        departments=[DepartmentRead.model_validate(row) for row in snapshot.departments],
        positions=[PositionRead.model_validate(row) for row in snapshot.positions],
        members=[
            MembershipRead(
                user_id=member.user_id,
                role=member.role,
                joined_at=member.joined_at,
                user=UserSummaryRead.model_validate(account),
                position_title=position.title if position is not None else None,
            )
            for member, account, position in snapshot.members
        ],
        placements=placements,
    )


@router.post(
    "/organizations/{organization_id}/departments",
    response_model=DepartmentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a department",
)
async def create_department(
    organization_id: UUID,
    payload: DepartmentCreate,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> DepartmentRead:
    department = await (await _org_structure(session, bus)).create_department(
        organization_id=organization_id,
        actor=user,
        name=payload.name,
        parent_id=payload.parent_id,
        description=payload.description,
    )
    await session.commit()
    return DepartmentRead.model_validate(department)


@router.patch(
    "/organizations/{organization_id}/departments/{department_id}",
    response_model=DepartmentRead,
    summary="Rename, re-parent or re-head a department",
)
async def update_department(
    organization_id: UUID,
    department_id: UUID,
    payload: DepartmentUpdate,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> DepartmentRead:
    repository = DepartmentRepository(session)
    department = await repository.get(department_id, organization_id=organization_id)
    if department is None:
        raise NotFoundError("Department not found")

    updated = await (await _org_structure(session, bus)).update_department(
        department,
        actor=user,
        name=payload.name,
        description=payload.description,
        parent_id=payload.parent_id,
        parent_set=payload.sent("parent_id"),
        head_id=payload.head_id,
        head_set=payload.sent("head_id"),
    )
    await session.commit()
    return DepartmentRead.model_validate(updated)


@router.delete(
    "/organizations/{organization_id}/departments/{department_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a department",
)
async def delete_department(
    organization_id: UUID,
    department_id: UUID,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = DepartmentRepository(session)
    department = await repository.get(department_id, organization_id=organization_id)
    if department is None:
        raise NotFoundError("Department not found")

    await (await _org_structure(session, bus)).delete_department(department, actor=user)
    await session.commit()


@router.post(
    "/organizations/{organization_id}/positions",
    response_model=PositionRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a position",
)
async def create_position(
    organization_id: UUID,
    payload: PositionCreate,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> PositionRead:
    position = await (await _org_structure(session, bus)).create_position(
        organization_id=organization_id,
        actor=user,
        title=payload.title,
        department_id=payload.department_id,
        description=payload.description,
        rank=payload.rank,
    )
    await session.commit()
    return PositionRead.model_validate(position)


@router.patch(
    "/organizations/{organization_id}/positions/{position_id}",
    response_model=PositionRead,
    summary="Update a position",
)
async def update_position(
    organization_id: UUID,
    position_id: UUID,
    payload: PositionUpdate,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> PositionRead:
    position = await PositionRepository(session).get(position_id, organization_id=organization_id)
    if position is None:
        raise NotFoundError("Position not found")

    updated = await (await _org_structure(session, bus)).update_position(
        position,
        actor=user,
        title=payload.title,
        description=payload.description,
        department_id=payload.department_id,
        department_set=payload.sent("department_id"),
        rank=payload.rank,
        rank_set=payload.sent("rank"),
    )
    await session.commit()
    return PositionRead.model_validate(updated)


@router.delete(
    "/organizations/{organization_id}/positions/{position_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a position",
)
async def delete_position(
    organization_id: UUID,
    position_id: UUID,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    repository = PositionRepository(session)
    position = await repository.get(position_id, organization_id=organization_id)
    if position is None:
        raise NotFoundError("Position not found")

    await (await _org_structure(session, bus)).delete_position(position, actor=user)
    await session.commit()


@router.patch(
    "/organizations/{organization_id}/members/{user_id}/placement",
    response_model=PlacementRead,
    summary="Place a member: department, position and manager",
)
async def place_member(
    organization_id: UUID,
    user_id: UUID,
    payload: MemberPlacementUpdate,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> PlacementRead:
    member = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user_id
    )
    if member is None:
        raise NotFoundError("That person is not a member of the organization")

    await (await _org_structure(session, bus)).place_member(
        member,
        actor=user,
        department_id=payload.department_id,
        department_set=payload.sent("department_id"),
        position_id=payload.position_id,
        position_set=payload.sent("position_id"),
        manager_id=payload.manager_id,
        manager_set=payload.sent("manager_id"),
    )
    await session.commit()

    deputies = await DeputyRepository(session).list_for(organization_id, user_id)
    return PlacementRead(
        user_id=user_id,
        department_id=member.department_id,
        position_id=member.position_id,
        manager_id=member.manager_id,
        deputies=deputies,
    )


@router.post(
    "/organizations/{organization_id}/members/{user_id}/deputies",
    status_code=status.HTTP_201_CREATED,
    summary="Record somebody as a deputy",
)
async def add_deputy(
    organization_id: UUID,
    user_id: UUID,
    payload: DeputyAdd,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await (await _org_structure(session, bus)).add_deputy(
        organization_id=organization_id,
        actor=user,
        user_id=user_id,
        deputy_id=payload.deputy_id,
    )
    await session.commit()


@router.delete(
    "/organizations/{organization_id}/members/{user_id}/deputies/{deputy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a deputy",
)
async def remove_deputy(
    organization_id: UUID,
    user_id: UUID,
    deputy_id: UUID,
    user: Annotated[User, Depends(require_permission("orgstructure.manage"))],
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await (await _org_structure(session, bus)).remove_deputy(
        organization_id=organization_id,
        actor=user,
        user_id=user_id,
        deputy_id=deputy_id,
    )
    await session.commit()
