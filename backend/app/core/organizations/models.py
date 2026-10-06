"""Organization, membership and team models.

An organization is the top-level isolation boundary
(docs/architecture.md, section 10): every project, team and activity row
carries ``organization_id``, and repositories filter on it, so a query cannot
leak across tenants even if a route forgets the check.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.core.permissions.roles import OrganizationRole
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, value_enum


class Organization(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "organizations"

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    #: Globally unique so that a URL always identifies exactly one tenant.
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[OrganizationMember]] = relationship(
        back_populates="organization",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Membership of a user in an organization, carrying the role."""

    __tablename__ = "organization_members"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[OrganizationRole] = mapped_column(
        value_enum(OrganizationRole, name="organization_role", length=16),
        nullable=False,
        default=OrganizationRole.MEMBER,
        server_default=OrganizationRole.MEMBER.value,
    )
    invited_by_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    organization: Mapped[Organization] = relationship(back_populates="members", lazy="noload")

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", name="uq_org_member_org_user"),
        Index("ix_organization_members_user_id", "user_id"),
    )


class Team(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "teams"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    members: Mapped[list[TeamMember]] = relationship(
        back_populates="team",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (Index("ix_teams_organization_id", "organization_id"),)

    def __repr__(self) -> str:
        return f"<Team {self.name}>"


class TeamMember(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "team_members"

    team_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("teams.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    team: Mapped[Team] = relationship(back_populates="members", lazy="noload")

    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_member_team_user"),
        Index("ix_team_members_user_id", "user_id"),
    )
