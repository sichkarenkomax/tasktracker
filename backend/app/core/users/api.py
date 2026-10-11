"""Users API: self-service profile, tenant-scoped lookups, portal directory.

Four audiences share this module, and the difference is only the guard:

* ``/users/me`` - the signed-in person, about themselves. No check beyond having
  a session.
* ``/users/{user_id}`` - a member of an organization, about a colleague. Guarded
  by that organization's ``user.view`` permission, and the contacts inside it are
  decided per request by the person's own visibility (stage 2.6).
* ``/users/{user_id}`` with ``PATCH`` - what an administrator may change about
  somebody: several permissions, all checked before anything is written
  (stage 2.18).
* ``/users`` - the installation's account directory, portal administrators only
  since stage 2.17. It used to be open to any signed-in account; that is a hole,
  not a convenience, and the merged people list
  (``GET /organizations/{id}/people``) is what answers "who is here" now.
"""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Query, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator

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
from app.core.organizations.service import org_structure_service, organization_service
from app.core.pagination import PageDep
from app.core.permissions.roles import OrganizationRole
from app.core.permissions.service import AuthorizationService
from app.core.users.models import PhoneKind, UserStatus
from app.core.users.repository import UserPhoneRepository, UserRepository
from app.core.users.service import UserService
from app.core.users.visibility import contacts_visibility, presence_visibility

router = APIRouter(prefix="/users", tags=["users"])


class PhoneRead(BaseModel):
    """One phone number as the API hands it out.

    Read straight off the row, so a caller never builds this by hand. The number
    is the plain form the server stores; the mask that groups it for reading is
    the screen's business (stage 2.8).
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    number: str
    kind: PhoneKind
    country: str | None = None


class PhoneWrite(BaseModel):
    """A number and what it is for.

    ``kind`` defaults to "work" because that is what a number in an office
    usually is, and because a field left empty on a form the person filled in
    carefully is a field the product decided for them.
    """

    model_config = ConfigDict(extra="forbid")

    number: str = Field(min_length=5, max_length=32)
    kind: PhoneKind = PhoneKind.WORK
    #: The two letters the number is written in (`"RU"`, `"US"`). Required for a
    #: national number, optional for one that already carries a `+`.
    country: str | None = Field(default=None, min_length=2, max_length=2)


class UserProfile(UserSummary):
    is_superuser: bool
    last_login_at: datetime | None = None
    #: When *this* person was last here (stage 2.9). No visibility question on
    #: one's own profile: the only person it would be hidden from is the one who
    #: asked.
    last_seen: datetime | None = None
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
    #: When they were last here, and whether this viewer is allowed to know it
    #: (stage 2.9). Two fields rather than one, because a missing timestamp and a
    #: withheld one are different facts: the first says "never", the second says
    #: "not yours to read", and a card that renders them the same way is lying in
    #: one of the two cases. `last_login_at` is withheld with it - see the route.
    last_seen: datetime | None = None
    last_seen_visible: bool = True
    department_id: UUID | None = None
    department_name: str | None = None
    position_id: UUID | None = None
    position_title: str | None = None
    #: Who this person reports to, so the editor can show the line that exists
    #: rather than an empty picker that would look like "nobody".
    manager_id: UUID | None = None
    role: str | None = None
    birthday: date | None = None
    phones: list[PhoneRead] = Field(default_factory=list)
    contacts_visible: bool = True
    #: The account's own state, and not the organization's: a locked login is
    #: locked everywhere, so the card says so before somebody tries to use it.
    status: str = UserStatus.ACTIVE.value
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
    ).add_phone(user, number=payload.number, kind=payload.kind, country=payload.country)
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
        user,
        phone=phone,
        number=payload.number,
        kind=payload.kind,
        country=payload.country,
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


@router.get(
    "",
    response_model=AdminUserPage,
    summary="Every account on the installation (portal administrators only)",
)
async def list_users(
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
    search: str | None = Query(default=None, max_length=200),
) -> AdminUserPage:
    """The installation's account directory.

    Portal administrators only, and that is a correction rather than a
    restriction added for the sake of it. This used to be open to anybody who
    could sign in, on the argument that a self-hosted installation is one
    company's own and browsing who is registered is a normal lookup - but it
    hands out every account's *address* across every tenant, which is exactly
    what a person's contacts visibility (stage 2.6) says they may withhold, and
    it answers a question the product now answers properly: the merged people
    list (``GET /organizations/{id}/people``) gives the members of one
    organization, with the contacts rules applied, and only a superuser sees the
    accounts that are outside it.

    Granting administrator rights has always been the narrower of the two: it
    changes rights over every tenant, so it is superuser-only and always was.
    """
    _require_superuser(user)
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
    # Membership of the organization, not merely the right to look inside it. The
    # permission above answers "may this reader read people"; it does not answer
    # "is this person one of them", and an account id on a shared installation is
    # guessable by anyone who has ever seen one. 404 rather than 403: the same
    # answer as a person who does not exist, so the route does not confirm that
    # the id belongs to somebody.
    membership = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user_id
    )
    if membership is None:
        raise NotFoundError("User not found")
    target = await UserRepository(session).get(user_id)
    if target is None:
        raise NotFoundError("User not found")

    # The address is a contact, and stage 2.6 lets a person withdraw it. This
    # route used to hand it out regardless while `/profile` obeyed, so the choice
    # existed with a second door beside it.
    contacts_visible = await contacts_visibility(session).viewer_may_see(
        viewer=user,
        person_id=user_id,
        organization_id=organization_id,
        viewer_role=await AuthorizationService(session).require_member(
            user=user, organization_id=organization_id
        ),
    )
    if contacts_visible:
        return UserSummary.model_validate(target)
    return UserSummary.model_validate(target).model_copy(update={"email": None})


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
    ``users.visibility``. A profile that answered 403 to somebody who may see
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
    # And it is also the tenant boundary. Without this the card belongs to any
    # account on the installation: the reader is checked against the
    # organization, the target never was. A person outside it gets the same
    # answer as a person who does not exist.
    if membership is None:
        raise NotFoundError("User not found")
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

    visible = await contacts_visibility(session).viewer_may_see(
        viewer=user, person_id=user_id, organization_id=organization_id, viewer_role=role
    )
    phones: list[PhoneRead] = []
    if visible:
        phones = [
            PhoneRead.model_validate(phone)
            for phone in await UserPhoneRepository(session).list_for(user_id)
        ]

    # Presence is its own question with its own answer (stage 2.9), and it takes
    # `last_login_at` with it: leaving the sign-in time visible to everybody while
    # hiding "when were you last here" would publish the same fact through the
    # back door, one column older.
    seen_by_viewer = await presence_visibility(session).viewer_may_see(
        viewer=user, person_id=user_id, organization_id=organization_id, viewer_role=role
    )

    return ProfileRead(
        id=target.id,
        email=target.email if visible else None,
        username=target.username,
        first_name=target.first_name,
        last_name=target.last_name,
        avatar_url=target.avatar_url,
        last_login_at=target.last_login_at if seen_by_viewer else None,
        last_seen=target.last_seen if seen_by_viewer else None,
        last_seen_visible=seen_by_viewer,
        department_id=membership.department_id if membership is not None else None,
        department_name=department_name,
        position_id=membership.position_id if membership is not None else None,
        position_title=position_title,
        manager_id=membership.manager_id if membership is not None else None,
        role=None if membership is None else str(membership.role),
        birthday=target.birthday if visible else None,
        phones=phones,
        contacts_visible=visible,
        status=str(target.status),
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


class AdminUserUpdate(BaseModel):
    """What an administrator may change about a member (stage 2.18).

    Every key is optional and an omitted key means "leave it alone" - including
    the nullable ones, which is why ``birthday`` uses a sentinel below rather
    than ``None``: "do not touch" and "remove the date" must be different
    requests, or a form that saves the name would quietly erase a birthday.
    """

    model_config = ConfigDict(extra="forbid")

    first_name: str | None = Field(default=None, max_length=64)
    last_name: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, min_length=3, max_length=320)
    #: Absent means "leave it"; explicit null means "remove it". See
    #: ``UNSET``.
    birthday: date | None = None
    #: ``disabled`` locks the account out of signing in; the other two statuses
    #: are the lifecycle's own and are not set by hand here.
    status: UserStatus | None = None
    #: Somebody's whole set of numbers, as the administrator sees it (2.18). A
    #: replacement rather than three calls, so a refused field cannot leave half
    #: a list behind - and omitted from the list means "this number is not theirs
    #: any more", which no other spelling of the request can say.
    phones: list[PhoneWrite] | None = None
    #: Organization facts, changed with their own permissions - see the route.
    role: OrganizationRole | None = None
    department_id: UUID | None = None
    position_id: UUID | None = None
    manager_id: UUID | None = None

    @model_validator(mode="after")
    def _at_least_one_field(self) -> AdminUserUpdate:
        fields = self.model_fields_set
        if not fields:
            raise ValueError("provide at least one field to change")
        return self

    @property
    def birthday_set(self) -> bool:
        return "birthday" in self.model_fields_set


@router.patch(
    "/{user_id}",
    response_model=UserProfile,
    summary="An administrator edits a member (name, email, birthday, status, role, placement)",
)
async def update_member(
    user_id: UUID,
    payload: AdminUserUpdate,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> UserProfile:
    """The one place an administrator changes another person (stage 2.18).

    One route rather than four, and the reason is atomicity: an editor with the
    name on one screen, the role on another and the address on a third would
    save half of what the administrator typed whenever one part was refused -
    a member renamed with the address left stale, or the reverse. Here every
    permission is checked *before* anything is written, so a request that is
    refused leaves the person exactly as they were, and the message says which
    part was not allowed.

    The permissions stay separate because the powers are separate:

    * ``user.update`` - the person's own data (name, address, birthday);
    * ``organization.members.manage`` plus a strictly higher rank - the role,
      because handing out rights is the one thing an equal rank may not do;
    * ``orgstructure.manage`` - where they sit in the org chart;
    * superuser - disabling the account, because a disabled login stops working
      in *every* organization this person belongs to, and a member of one
      organization must not be able to do that.
    """
    authorization = AuthorizationService(session)
    member = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=user_id
    )
    target = await UserRepository(session).get(user_id)
    if target is None or member is None:
        raise NotFoundError("User not found")

    repository = UserRepository(session)
    service = UserService(repository, bus, UserPhoneRepository(session))

    wants_role = payload.role is not None and payload.role != member.role
    wants_placement = any(
        field in payload.model_fields_set
        for field in ("department_id", "position_id", "manager_id")
    )
    wants_status = payload.status is not None and payload.status is not target.status

    # Every check first, every write after: see the docstring.
    if wants_role:
        await authorization.require_manage_member(
            user=user,
            organization_id=organization_id,
            target_user_id=user_id,
            target_role=member.role,
            new_role=payload.role,  # not None whenever `wants_role` is true
        )
    if wants_placement:
        await authorization.require_permission(
            user=user, organization_id=organization_id, permission="orgstructure.manage"
        )
    if wants_status and not user.is_superuser:
        raise PermissionDeniedError(
            "Only a portal administrator may change an account's status",
            details={"status": str(payload.status)},
        )
    if user.id == user_id and payload.email is not None:
        # The same rule as `set_member_email`: one's own address is a separate
        # question this stage leaves alone, and one route that answered it by
        # accident would answer it for everybody.
        raise PermissionDeniedError(
            "Changing your own email is not available here",
            details={"hint": "ask an administrator"},
        )
    account_fields = {
        "first_name": payload.first_name,
        "last_name": payload.last_name,
    }
    wants_phones = payload.phones is not None
    if any(value is not None for value in account_fields.values()) or wants_phones:
        await authorization.require_permission(
            user=user, organization_id=organization_id, permission="user.update"
        )

    if payload.email is not None and payload.email.strip() != target.email:
        await authorization.require_permission(
            user=user, organization_id=organization_id, permission="user.update"
        )
        await service.change_email(
            target=target, actor=user, organization_id=organization_id, email=payload.email
        )
    if any(value is not None for value in account_fields.values()):
        await service.update_profile(
            target,
            first_name=account_fields["first_name"],
            last_name=account_fields["last_name"],
        )
    if payload.birthday_set and payload.birthday != target.birthday:
        # Checked here, written below, like every other field: the birthday is
        # the person's own record, and a plain member writing into someone
        # else's is what the audit caught. Guarding a field because it is easy to
        # forget is not a plan, so the rule is stated instead: **every field of
        # this schema passes through a check**, and the test says which field is
        # being written when it fails.
        await authorization.require_permission(
            user=user, organization_id=organization_id, permission="user.update"
        )
        await service.set_birthday(target, birthday=payload.birthday)
    if wants_phones:
        # Checked above, written here: the numbers are normalized (and refused
        # for being too short or too long) before the first row changes.
        assert payload.phones is not None
        await service.replace_phones(
            target,
            numbers=[(phone.number, phone.kind, phone.country) for phone in payload.phones],
        )
    if wants_status:
        assert payload.status is not None
        await service.set_status(
            target=target, status=payload.status, actor=user, organization_id=organization_id
        )

    if wants_role:
        organization = await OrganizationRepository(session).get(organization_id)
        assert organization is not None  # the membership row proves it exists
        await organization_service(session, bus).change_member_role(
            organization=organization,
            member=member,
            new_role=payload.role,  # type: ignore[arg-type]  # checked by `wants_role`
            actor=user,
        )
    if wants_placement:
        await org_structure_service(session, bus).place_member(
            member,
            actor=user,
            department_id=payload.department_id,
            department_set="department_id" in payload.model_fields_set,
            position_id=payload.position_id,
            position_set="position_id" in payload.model_fields_set,
            manager_id=payload.manager_id,
            manager_set="manager_id" in payload.model_fields_set,
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
