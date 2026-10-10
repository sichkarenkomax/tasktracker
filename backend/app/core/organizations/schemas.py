"""Pydantic schemas: organizations, memberships and teams."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.core.permissions.roles import OrganizationRole

SLUG_PATTERN = r"^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$"


def slugify(value: str) -> str:
    """Derive a URL-safe slug from a display name.

    Only ASCII letters and digits survive: a slug ends up in a URL path, and
    ``Ökonomie`` must not become a percent-encoded surprise. Transliteration is
    deliberately out of scope - the organization owner can always pass an
    explicit slug.
    """
    out = [
        char if (char.isascii() and (char.isalnum() or char == "-")) else "-"
        for char in value.strip().lower()
    ]
    slug = "".join(out).strip("-")
    while "--" in slug:
        slug = slug.replace("--", "-")
    return slug[:80].strip("-")


class OrganizationCreate(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    slug: str | None = Field(default=None, pattern=SLUG_PATTERN)
    description: str | None = Field(default=None, max_length=2000)

    def resolved_slug(self) -> str:
        return self.slug or slugify(self.name)


class OrganizationUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=2, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class OrganizationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    slug: str
    description: str | None
    created_at: datetime
    updated_at: datetime


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: UUID
    role: OrganizationRole
    joined_at: datetime | None
    user: UserSummaryRead | None = None
    #: The org-structure position this member holds, as a title (stage 2.5). None
    #: is a normal answer - most members hold none - and is why the picker shows
    #: the position only when there is one.
    position_title: str | None = None


class UserSummaryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    username: str
    first_name: str | None
    last_name: str | None
    avatar_url: str | None


class MemberAdd(BaseModel):
    """Add a member identified either by id or by email, never by both."""

    user_id: UUID | None = None
    email: str | None = None
    role: OrganizationRole = OrganizationRole.MEMBER

    @model_validator(mode="after")
    def exactly_one_identifier(self) -> MemberAdd:
        if (self.user_id is None) == (self.email is None):
            raise ValueError("provide exactly one of user_id or email")
        return self


class MemberRoleUpdate(BaseModel):
    role: OrganizationRole


# --- the merged people list (stage 2.17) ---------------------------------------


class PersonRead(BaseModel):
    """One row of the merged list.

    The account on one side, this organization's facts about it on the other,
    and the two are nullable independently: ``in_organization`` false means the
    row exists only as an account on this installation, and ``email`` is null
    whenever the viewer may not read that person's contacts (stage 2.6) - which
    is why ``contacts_visible`` travels with it rather than being inferred from
    an empty cell.
    """

    id: UUID
    username: str
    first_name: str | None = None
    last_name: str | None = None
    avatar_url: str | None = None
    email: str | None = None
    status: str
    last_login_at: datetime | None = None
    #: "Last seen" rather than "last signed in" (stage 2.9), and whether the
    #: viewer may read it. Kept apart for the same reason as ``email``: a person
    #: who has never been seen and a person whose answer hides it are different
    #: rows, and a blank cell cannot say which one it is.
    last_seen: datetime | None = None
    last_seen_visible: bool = True
    created_at: datetime
    birthday: str | None = None
    contacts_visible: bool = True

    in_organization: bool
    role: OrganizationRole | None = None
    joined_at: datetime | None = None
    department_id: UUID | None = None
    department_name: str | None = None
    position_id: UUID | None = None
    position_title: str | None = None


class PeoplePageRead(BaseModel):
    items: list[PersonRead]
    total: int
    limit: int
    offset: int


# --- organization structure -------------------------------------------------


class OrgWriteModel(BaseModel):
    """Base for the org chart's writes.

    Unknown fields are rejected rather than dropped, for the same reason the
    Tasks module does it: a typo has to be reported, not silently ignored while
    the request reports success.
    """

    model_config = ConfigDict(extra="forbid")


class DepartmentCreate(OrgWriteModel):
    name: str = Field(min_length=1, max_length=200)
    #: Null means a top-level department. Sending null and omitting the key mean
    #: different things on update, which is why the update has its own model.
    parent_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)


class DepartmentUpdate(OrgWriteModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    parent_id: UUID | None = None
    head_id: UUID | None = None

    def sent(self, field: str) -> bool:
        """Was this key actually present in the request?

        ``model_fields_set`` is the only way to tell "clear the parent" from
        "leave the parent alone", and every nullable field on this model needs the
        distinction - otherwise saving a name would silently promote a department
        to the top of the chart.
        """
        return field in self.model_fields_set


class DepartmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    parent_id: UUID | None
    head_id: UUID | None
    position: int


class PositionCreate(OrgWriteModel):
    title: str = Field(min_length=1, max_length=200)
    #: Null makes the title organization-wide.
    department_id: UUID | None = None
    description: str | None = Field(default=None, max_length=2000)
    rank: int | None = None


class PositionUpdate(OrgWriteModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)
    department_id: UUID | None = None
    rank: int | None = None

    def sent(self, field: str) -> bool:
        return field in self.model_fields_set


class PositionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    title: str
    description: str | None
    department_id: UUID | None
    rank: int | None


class MemberPlacementUpdate(OrgWriteModel):
    """Where one person sits: department, position and reporting line.

    All three are optional and independent - somebody can report to a manager
    without being in a department yet, which is the normal state on day one.
    """

    department_id: UUID | None = None
    position_id: UUID | None = None
    manager_id: UUID | None = None

    def sent(self, field: str) -> bool:
        return field in self.model_fields_set


class PlacementRead(BaseModel):
    """One person's place in the chart, resolved for display."""

    user_id: UUID
    department_id: UUID | None
    position_id: UUID | None
    manager_id: UUID | None
    deputies: list[UUID] = Field(default_factory=list)


class OrgStructureRead(BaseModel):
    """Everything the chart draws, in one response.

    One request rather than one per node: on a real organization the editor would
    otherwise spend a hundred round trips before drawing anything, and every one
    of them could see a different version.
    """

    departments: list[DepartmentRead]
    positions: list[PositionRead]
    members: list[MembershipRead]
    placements: dict[UUID, PlacementRead]


class DeputyAdd(OrgWriteModel):
    deputy_id: UUID


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class TeamUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=200)
    description: str | None = Field(default=None, max_length=2000)


class TeamRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
    member_ids: list[UUID] = Field(default_factory=list)


class TeamMemberAdd(BaseModel):
    user_id: UUID


MembershipRead.model_rebuild()
