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

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.auth.schemas import UserSummary
from app.core.dependencies import EventBusDep
from app.core.errors import NotFoundError, PermissionDeniedError
from app.core.files.service import file_service
from app.core.organizations.repository import (
    DepartmentRepository,
    OrganizationRepository,
    PositionRepository,
)
from app.core.pagination import PageDep
from app.core.permissions.service import AuthorizationService
from app.core.users.repository import UserPhoneRepository, UserRepository
from app.core.users.service import UserService
from app.core.users.visibility import ContactsVisibility

router = APIRouter(prefix="/users", tags=["users"])


class PhoneRead(BaseModel):
    """One phone number as the API hands it out.

    Read straight off the row, so a caller never builds this by hand.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    comment: str | None = None


class UserProfile(UserSummary):
    is_superuser: bool
    last_login_at: datetime | None = None
    #: Contacts, present only when the viewer may read them (stage 2.6). A null
    #: date means "there is none to show"; a profile whose contacts are withheld
    #: leaves ``contacts_visible`` false and says so, rather than sending empty
    #: fields that look like empty answers.
    birthday: date | None = None
    phones: list[PhoneRead] = Field(default_factory=list)
    contacts_visible: bool = True


class ProfileRead(BaseModel):
    """Somebody else's profile (stage 2.6).

    Name, department, position and avatar are always here - they are how you
    find out who to ask, and every member of the organization reads them. The
    contacts below are the part the visibility rules decide on, per request.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str | None = None
    username: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    last_login_at: datetime | None = None
    department_id: UUID | None = None
    department_name: str | None = None
    position_id: UUID | None = None
    position_title: str | None = None
    role: str | None = None
    birthday: date | None = None
    phones: list[PhoneRead] = []
    contacts_visible: bool = True
    #: Always false in v1: chat arrives in stage 8, and a button that cannot do
    #: anything is worse than no button. The profile says so in the UI.
    can_message: bool = False


class UserProfileUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    #: A reference to one of the caller's own files, never a URL: the server
    #: decides where a picture is read from and who may see it (stage 2.3).
    #: Omitting the key leaves the avatar alone; the file itself, deleted
    #: through the files API, clears it via the foreign key.
    avatar_file_id: UUID | None = None


class BirthdayUpdate(BaseModel):
    """Writing or clearing the birthday (stage 2.8).

    Its own payload because ``UserProfileUpdate`` reads a missing key as "leave
    it alone", and a person who wants the date *gone* has to be able to say so
    without also touching their name.
    """

    model_config = ConfigDict(extra="forbid")

    birthday: date | None = None


class PhoneWrite(BaseModel):
    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=3, max_length=32)
    comment: str | None = Field(default=None, max_length=120)


class AdminEmailUpdate(BaseModel):
    """An administrator changes somebody's address (stage 2.7)."""

    model_config = ConfigDict(extra="forbid")

    email: str = Field(min_length=3, max_length=320)


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
    await UserService(UserRepository(session), bus, UserPhoneRepository(session)).update_profile(
        user,
        first_name=payload.first_name,
        last_name=payload.last_name,
        avatar_file_id=payload.avatar_file_id,
    )
    await session.commit()
    return UserProfile.model_validate(user)


@router.patch("/me/birthday", response_model=UserProfile, summary="Write or clear own birthday")
async def update_own_birthday(
    payload: BirthdayUpdate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> UserProfile:
    await UserService(UserRepository(session), bus, UserPhoneRepository(session)).set_birthday(
        user, birthday=payload.birthday
    )
    await session.commit()
    return UserProfile.model_validate(user)


@router.get("/me/phones", response_model=list[PhoneRead], summary="Own phone numbers")
async def list_own_phones(user: CurrentUser, session: SessionDep) -> list[PhoneRead]:
    """A person's own phones, in the order they wrote them.

    No permission check: this is the signed-in person about themselves, the
    same audience as ``/users/me`` itself.
    """
    phones = await UserPhoneRepository(session).list_for(user.id)
    return [PhoneRead.model_validate(phone) for phone in phones]


@router.post("/me/phones", response_model=PhoneRead, summary="Add a phone number")
async def add_own_phone(
    payload: PhoneWrite,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> PhoneRead:
    stored = await UserService(
        UserRepository(session), bus, UserPhoneRepository(session)
    ).add_phone(user, number=payload.number, comment=payload.comment)
    await session.commit()
    return PhoneRead.model_validate(stored)


@router.patch("/me/phones/{phone_id}", response_model=PhoneRead, summary="Edit a phone number")
async def update_own_phone(
    phone_id: UUID,
    payload: PhoneWrite,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> PhoneRead:
    repository = UserPhoneRepository(session)
    phone = await repository.get_for_user(phone_id=phone_id, user_id=user.id)
    if phone is None:
        # Someone else's number is not found rather than forbidden: the route
        # never has to admit that the id exists.
        raise NotFoundError("Phone number not found")
    stored = await UserService(UserRepository(session), bus, repository).update_phone(
        user, phone=phone, number=payload.number, comment=payload.comment
    )
    await session.commit()
    return PhoneRead.model_validate(stored)


@router.delete("/me/phones/{phone_id}", status_code=204, summary="Remove a phone number")
async def delete_own_phone(
    phone_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> Response:
    repository = UserPhoneRepository(session)
    phone = await repository.get_for_user(phone_id=phone_id, user_id=user.id)
    if phone is None:
        raise NotFoundError("Phone number not found")
    await UserService(UserRepository(session), bus, repository).delete_phone(user, phone=phone)
    await session.commit()
    return Response(status_code=204)


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


@router.get("/{user_id}/profile", response_model=ProfileRead, summary="A member's profile")
async def read_profile(
    user_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> ProfileRead:
    """The card behind a colleague's name (stage 2.6).

    Two audiences in one response, and the difference is which fields are
    filled rather than a second route: the name, department, position and avatar
    are always here, while the contacts are decided per request by
    ``ContactsVisibility``. A profile that answered 403 to somebody who may see
    the name but not the phone would make the roster full of links that fail.
    """
    role = await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="user.view"
    )
    repository = UserRepository(session)
    target = await repository.get(user_id)
    if target is None:
        raise NotFoundError("User not found")

    # The placement is an organization fact, so it comes from the organization's
    # own table rather than being asked for a second time by the frontend.
    membership = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user_id
    )
    department_name = None
    position_title = None
    if membership is not None and membership.department_id is not None:
        department = await DepartmentRepository(session).get(
            membership.department_id, organization_id=organization_id
        )
        department_name = department.name if department is not None else None
    if membership is not None and membership.position_id is not None:
        position = await PositionRepository(session).get(
            membership.position_id, organization_id=organization_id
        )
        position_title = position.title if position is not None else None

    visible = await ContactsVisibility(session).viewer_may_see(
        viewer=user, person_id=user_id, organization_id=organization_id, viewer_role=role
    )
    phones: list[PhoneRead] = []
    if visible:
        phones = [
            PhoneRead.model_validate(phone)
            for phone in await UserPhoneRepository(session).list_for(user_id)
        ]

    return ProfileRead(
        id=target.id,
        email=target.email if visible else None,
        username=target.username,
        first_name=target.first_name,
        last_name=target.last_name,
        avatar_url=target.avatar_url,
        last_login_at=target.last_login_at,
        department_id=membership.department_id if membership is not None else None,
        department_name=department_name,
        position_id=membership.position_id if membership is not None else None,
        position_title=position_title,
        role=None if membership is None else str(membership.role),
        birthday=target.birthday if visible else None,
        phones=phones,
        contacts_visible=visible,
    )


@router.patch(
    "/{user_id}/email",
    response_model=UserProfile,
    summary="An administrator changes a member's email",
)
async def set_member_email(
    user_id: UUID,
    payload: AdminEmailUpdate,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> UserProfile:
    """Stage 2.7: an administrator fixes somebody's address.

    Guarded by ``user.update`` - the permission an organization already uses for
    "this member may be changed", not a new one invented for this route. The
    person whose address is being changed cannot do this to themselves: changing
    one's own email is a separate question that this stage explicitly leaves
    alone, and a route that quietly accepted it would answer that question
    without anybody deciding to.
    """
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="user.update"
    )
    if user.id == user_id:
        raise PermissionDeniedError(
            "Changing your own email is not available here",
            details={"hint": "ask an administrator"},
        )
    repository = UserRepository(session)
    target = await repository.get(user_id)
    if target is None:
        raise NotFoundError("User not found")
    # The change is about a member of this organization, so a person who is not
    # one cannot be changed "through" it.
    member = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user_id
    )
    if member is None:
        raise NotFoundError("User not found")

    await UserService(repository, bus, UserPhoneRepository(session)).change_email(
        target=target, actor=user, organization_id=organization_id, email=payload.email
    )
    await session.commit()
    return UserProfile.model_validate(target)


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
