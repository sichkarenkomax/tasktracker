"""Settings API: organization-wide, and the caller's own."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.errors import PermissionDeniedError
from app.core.organizations.repository import OrganizationRepository
from app.core.permissions.service import AuthorizationService
from app.core.settings.service import (
    PersonalSettingsService,
    SettingsService,
    definitions,
    personal_definitions,
)

router = APIRouter(tags=["settings"])


class SettingsRead(BaseModel):
    organization_id: UUID
    values: dict[str, object]
    available: dict[str, dict[str, object]]


class SettingsUpdate(BaseModel):
    values: dict[str, object] = Field(default_factory=dict)


class PersonalSettingsRead(BaseModel):
    """The caller's settings, and - importantly - what they actually chose.

    ``values`` is defaults merged with stored overrides, which is the right thing
    to read and the wrong thing to *decide* with: a merged default is
    indistinguishable from a choice, so a client that honours it would pin every
    person to the default and leave the portal's own setting unreachable. ``stored``
    holds only the rows that exist, which answers "did they pick one" honestly.
    """

    organization_id: UUID
    values: dict[str, object]
    stored: dict[str, object]
    available: dict[str, dict[str, object]]


class PersonalSettingsUpdate(BaseModel):
    values: dict[str, object] = Field(default_factory=dict)


async def _require_member(session: SessionDep, user: CurrentUser, organization_id: UUID) -> None:
    """Membership, not a permission: these are the caller's own settings.

    There is nothing here to authorize beyond "you belong here" - a person may
    always write their own preferences - so this is the check the preferences
    screen needs and no more.
    """
    member = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user.id
    )
    if member is None:
        raise PermissionDeniedError("You are not a member of this organization")


@router.get(
    "/organizations/{organization_id}/settings",
    response_model=SettingsRead,
    summary="Effective organization settings",
)
async def read_settings(
    organization_id: UUID, user: CurrentUser, session: SessionDep
) -> SettingsRead:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.view"
    )
    return SettingsRead(
        organization_id=organization_id,
        values=await SettingsService(session).read(organization_id),
        available=definitions(),
    )


@router.put(
    "/organizations/{organization_id}/settings",
    response_model=SettingsRead,
    summary="Update organization settings",
)
async def update_settings(
    organization_id: UUID,
    payload: SettingsUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> SettingsRead:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.settings.manage"
    )
    service = SettingsService(session)
    values = await service.write(organization_id, payload.values)
    await session.commit()
    return SettingsRead(organization_id=organization_id, values=values, available=definitions())


@router.get(
    "/users/me/settings",
    response_model=PersonalSettingsRead,
    summary="The caller's own settings in one organization",
)
async def read_personal_settings(
    organization_id: UUID, user: CurrentUser, session: SessionDep
) -> PersonalSettingsRead:
    await _require_member(session, user, organization_id)
    service = PersonalSettingsService(session)
    return PersonalSettingsRead(
        organization_id=organization_id,
        values=await service.read(organization_id, user.id),
        stored=await service.stored(organization_id, user.id),
        available=personal_definitions(),
    )


@router.put(
    "/users/me/settings",
    response_model=PersonalSettingsRead,
    summary="Update the caller's own settings",
)
async def update_personal_settings(
    organization_id: UUID,
    payload: PersonalSettingsUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> PersonalSettingsRead:
    await _require_member(session, user, organization_id)
    service = PersonalSettingsService(session)
    values = await service.write(organization_id, user.id, payload.values)
    await session.commit()
    return PersonalSettingsRead(
        organization_id=organization_id,
        values=values,
        stored=await service.stored(organization_id, user.id),
        available=personal_definitions(),
    )
