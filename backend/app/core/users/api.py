"""Users API: self-service profile and tenant-scoped lookups.

There is deliberately no global user directory: browsing people happens through
``GET /organizations/{organization_id}/members``, which is already scoped by the
authorization check (docs/architecture.md, section 10).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.auth.schemas import UserSummary
from app.core.dependencies import EventBusDep
from app.core.errors import NotFoundError
from app.core.permissions.service import AuthorizationService
from app.core.users.repository import UserRepository
from app.core.users.service import UserService

router = APIRouter(prefix="/users", tags=["users"])


class UserProfile(UserSummary):
    is_superuser: bool
    last_login_at: datetime | None = None


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    avatar_url: str | None = Field(default=None, max_length=512)


@router.get("/me", response_model=UserProfile, summary="Current user profile")
async def read_me(user: CurrentUser) -> UserProfile:
    return UserProfile.model_validate(user)


@router.patch("/me", response_model=UserProfile, summary="Update own profile")
async def update_me(
    payload: UserProfileUpdate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> UserProfile:
    await UserService(UserRepository(session), bus).update_profile(
        user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        avatar_url=payload.avatar_url,
    )
    await session.commit()
    return UserProfile.model_validate(user)


@router.get("/{user_id}", response_model=UserSummary, summary="User by id")
async def read_user(
    user_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> UserSummary:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="user.view"
    )
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise NotFoundError("User not found")
    return UserSummary.model_validate(target)
