"""Organization settings API."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.permissions.service import AuthorizationService
from app.core.settings.service import SettingsService, definitions

router = APIRouter(tags=["settings"])


class SettingsRead(BaseModel):
    organization_id: UUID
    values: dict[str, object]
    available: dict[str, dict[str, object]]


class SettingsUpdate(BaseModel):
    values: dict[str, object] = Field(default_factory=dict)


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
