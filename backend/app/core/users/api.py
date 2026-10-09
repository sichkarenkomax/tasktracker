"""Users API: self-service profile, tenant-scoped lookups, portal directory.

Three different audiences share this module, and the difference is only the guard:

* ``/users/me`` - the signed-in person, about themselves. No check beyond having
  a session.
* ``/users/{user_id}`` - a member of an organization, about a colleague. Guarded
  by that organization's ``user.view`` permission.
* ``/users`` - the portal directory, open to any signed-in account: on a
  self-hosted installation every tenant is the same deployment, and browsing who
  is registered is a normal lookup. Only ``/users/{user_id}/superuser`` stays
  superuser-only - granting rights over every tenant is a portal action, unlike
  looking at the list.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.auth.schemas import UserSummary
from app.core.dependencies import EventBusDep
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.files.service import file_service
from app.core.pagination import PageDep
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
    #: A reference to one of the caller's own files, never a URL: the server
    #: decides where a picture is read from and who may see it (stage 2.3).
    #: Omitting the key leaves the avatar alone; the file itself, deleted
    #: through the files API, clears it via the foreign key.
    avatar_file_id: UUID | None = None


class AdminUserRead(UserSummary):
    """An account as the portal administrator sees it."""

    is_superuser: bool
    created_at: datetime
    last_login_at: datetime | None = None


class AdminUserPage(BaseModel):
    items: list[AdminUserRead]
    total: int
    limit: int
    offset: int


class SuperuserUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_superuser: bool


def _require_superuser(user: CurrentUser) -> None:
    """The guard on the one route that changes rights over every tenant.

    ``is_superuser`` is a column rather than an organization role on purpose: an
    administrator of the installation is a different thing from an administrator
    of one organization, and conflating them would let an org admin promote
    themselves over every other tenant.
    """
    if not user.is_superuser:
        raise PermissionDeniedError("Portal administrator rights required")


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
    if payload.avatar_file_id is not None:
        # Binding is where "whose file is this, and is it a picture?" gets
        # answered; the read side answers "may this viewer see it?" per
        # request instead of trusting a URL written once at upload time.
        await file_service(session).require_owned_image(payload.avatar_file_id, owner_id=user.id)
    await UserService(UserRepository(session), bus).update_profile(
        user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        avatar_file_id=payload.avatar_file_id,
    )
    await session.commit()
    return UserProfile.model_validate(user)


@router.get("", response_model=AdminUserPage, summary="Every account on the installation")
async def list_users(
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
    search: str | None = Query(default=None, max_length=200),
) -> AdminUserPage:
    repository = UserRepository(session)
    accounts = await repository.search(term=search, limit=page.limit, offset=page.offset)
    return AdminUserPage(
        items=[AdminUserRead.model_validate(account) for account in accounts],
        total=await repository.count(),
        limit=page.limit,
        offset=page.offset,
    )


@router.patch(
    "/{user_id}/superuser",
    response_model=AdminUserRead,
    summary="Grant or revoke portal administrator rights",
)
async def set_superuser(
    user_id: UUID,
    payload: SuperuserUpdate,
    user: CurrentUser,
    session: SessionDep,
) -> AdminUserRead:
    _require_superuser(user)
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise NotFoundError("User not found")
    if not payload.is_superuser and target.id == user.id:
        # Otherwise the last administrator can demote themselves and lock
        # everybody - including, if it came to it, the fix - out of this screen.
        raise PermissionDeniedError("You cannot remove your own administrator rights")
    if target.is_superuser != payload.is_superuser:
        target.is_superuser = payload.is_superuser
        await session.commit()
    return AdminUserRead.model_validate(target)


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


@router.get("/{user_id}/avatar", summary="A person's avatar image")
async def read_avatar(
    user_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    """Serve the bytes behind ``avatar_url``, deciding permission per request.

    This is the half the stored URL used to skip: the profile only remembers
    *which file* the picture is, and every read checks that the viewer may see
    the organization that file belongs to - the same ``user.view`` bar as the
    profile itself. An outsider gets 403 rather than a picture, and a file
    deleted from the files API simply stops resolving (the foreign key clears
    the avatar), so no response ever points at nothing.
    """
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise NotFoundError("User not found")
    if target.avatar_file_id is None:
        # Deliberately the same shape as "no such user": whether somebody has
        # a picture is not information this route hands out.
        raise NotFoundError("User not found")
    row = await file_service(session).find(target.avatar_file_id)
    if row is None:
        # Unreachable while the foreign key holds, but a missing row must not
        # become a 500 if it ever happens.
        raise NotFoundError("User not found")
    await AuthorizationService(session).require_permission(
        user=user, organization_id=row.organization_id, permission="user.view"
    )
    data = await file_service(session).read(row)
    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            # Images only ever land here (see ``require_owned_image``), and
            # nosniff keeps the bytes from being reinterpreted on our origin.
            "X-Content-Type-Options": "nosniff",
            # The URL carries the file id as a version, so this may be kept
            # for a while without ever showing a previous picture.
            "Cache-Control": "private, max-age=3600",
        },
    )
