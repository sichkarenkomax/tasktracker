"""Organization, membership and team models.

An organization is the top-level isolation boundary
(docs/architecture.md, section 10): every project, team and activity row
carries ``organization_id``, and repositories filter on it, so a query cannot
leak across tenants even if a route forgets the check.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
    departments: Mapped[list[Department]] = relationship(
        cascade="all, delete-orphan",
        lazy="noload",
    )
    positions: Mapped[list[OrgPosition]] = relationship(
        cascade="all, delete-orphan",
        lazy="noload",
    )

    def __repr__(self) -> str:
        return f"<Organization {self.slug}>"


class OrganizationMember(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Membership of a user in an organization, carrying the role.

    The last three columns are the org chart: which department somebody is in,
    what they do, and who they report to. They live on the membership rather
    than in a side table because they are attributes of *this person's place in
    this organization* - the same user is somebody else entirely in another
    tenant, and a separate table would make it possible to record a job for
    somebody who is not a member.
    """

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
    #: The department this person belongs to. Null means "not placed on the chart
    #: yet", which is the normal state on day one and not an error.
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("org_departments.id", ondelete="SET NULL"),
    )
    #: What they do. A position carries its own optional department, so a title
    #: can be scoped ("Backend developer" inside Engineering) or org-wide
    #: ("Chief executive").
    position_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("org_positions.id", ondelete="SET NULL"),
    )
    #: Who they report to. Null is the top of the chart.
    manager_id: Mapped[UUID | None] = mapped_column(
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
        # The chart is read as "everything in this department" and as "everyone
        # reporting to this person", so both columns are indexed.
        Index("ix_organization_members_department_id", "department_id"),
        Index("ix_organization_members_manager_id", "manager_id"),
    )


class Department(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A node in the department tree.

    ``parent_id`` makes this a tree rather than a list, because a real
    organization is nested - Engineering containing Backend, Backend containing
    Platform - and flattening it would force every reader to rebuild the hierarchy
    that is already known here.

    A cycle is impossible in the database but not self-evident: ``a -> b -> a``
    satisfies every foreign key. The service walks the parent chain before
    writing and refuses the move, which is the only place that knows what
    "ancestor" means.
    """

    __tablename__ = "org_departments"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: The department above this one; null is the top of the chart.
    parent_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("org_departments.id", ondelete="SET NULL"),
    )
    #: Who runs this department. Distinct from ``manager_id`` on a member: this is
    #: "heads the department", which is a fact about the unit, not a reporting
    #: line, and survives the person leaving.
    head_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    #: Sibling order. Explicit rather than alphabetical, because "Backend" before
    #: "Frontend" is a decision somebody made and not one the alphabet makes.
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

    __table_args__ = (
        UniqueConstraint("organization_id", name, name="uq_org_department_org_name"),
        Index("ix_org_departments_organization_id", "organization_id"),
        Index("ix_org_departments_parent_id", "parent_id"),
    )

    def __repr__(self) -> str:
        return f"<Department {self.name!r}>"


class OrgPosition(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A job title, optionally scoped to one department.

    Named ``OrgPosition`` rather than ``Position`` because the unprefixed name
    collides with anything that wants to talk about a person's place in the
    hierarchy, and because "position" is also the sibling-order column.
    """

    __tablename__ = "org_positions"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    #: Null makes the title organization-wide, which is right for the handful of
    #: roles above the departments and wrong for everything below them.
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("org_departments.id", ondelete="SET NULL"),
    )
    #: Rank, for drawing the chart top-down. Higher is closer to the top; null
    #: sorts last so an unset rank never quietly outranks a deliberate one.
    rank: Mapped[int | None] = mapped_column(Integer)

    __table_args__ = (
        UniqueConstraint("organization_id", title, name="uq_org_position_org_title"),
        Index("ix_org_positions_organization_id", "organization_id"),
        Index("ix_org_positions_department_id", "department_id"),
    )

    def __repr__(self) -> str:
        return f"<OrgPosition {self.title!r}>"


class MemberDeputy(UUIDPrimaryKeyMixin, Base):
    """Somebody who acts for another person while they are away.

    A separate table rather than a column because the relation is many-to-many:
    a director has a deputy and a deputy for two directors, and "who covers for
    whom" is not derivable from the reporting tree. Deputies do not inherit any
    permission - the point is to record who to call, not to widen access.
    """

    __tablename__ = "org_deputies"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The person being covered for.
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    #: The person who covers.
    deputy_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    __table_args__ = (
        UniqueConstraint(
            "organization_id", "user_id", "deputy_id", name="uq_org_deputy_user_deputy"
        ),
        Index("ix_org_deputies_user_id", "user_id"),
        Index("ix_org_deputies_deputy_id", "deputy_id"),
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
