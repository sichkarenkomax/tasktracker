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
