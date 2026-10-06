"""Project model.

Core owns projects because Tasks, Kanban, Gantt and Scrum all attach to them
(docs/architecture.md, sections 12, 32, 33, 34).
"""

from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from sqlalchemy import ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, value_enum


class ProjectStatus(StrEnum):
    PLANNED = "planned"
    ACTIVE = "active"
    ON_HOLD = "on_hold"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class Project(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "projects"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[ProjectStatus] = mapped_column(
        value_enum(ProjectStatus, name="project_status", length=16),
        nullable=False,
        default=ProjectStatus.PLANNED,
        server_default=ProjectStatus.PLANNED.value,
    )

    #: Creator, always a member of the same organization.
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        # RESTRICT rather than CASCADE: deleting an account must never silently
        # take a project with it.
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    __table_args__ = (Index("ix_projects_organization_id", "organization_id"),)

    def __repr__(self) -> str:
        return f"<Project {self.name}>"
