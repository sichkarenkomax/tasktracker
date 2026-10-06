"""Task and Comment models.

Tasks is the first functional module, and the only place besides Core that owns
tables (docs/architecture.md, sections 13, 14, 18). Nothing here is imported by
Core: the module reaches the platform through services, permissions and the event
bus only, which is what keeps the boundary in section 64 intact.
"""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Date, DateTime, ForeignKey, Index, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, value_enum

#: Operator class for the trigram GIN indexes below. SQLAlchemy ships no named
#: export for PostgreSQL's contrib operator classes, so the name is passed as a
#: string and rendered verbatim into DDL. It resolves only once ``pg_trgm`` is
#: installed, which is why the migration creates the extension first.
GIN_TRGM_OPS = "gin_trgm_ops"


class TaskStatus(StrEnum):
    """Task lifecycle.

    Section 15 asks for exactly three statuses and explicitly requires that
    custom statuses stay possible later. ``value_enum`` stores a ``VARCHAR`` with
    a CHECK, so adding a status is an ordinary constraint change rather than an
    ``ALTER TYPE`` - and when per-organization custom statuses arrive, the CHECK
    is the only thing that has to give way.
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


#: Statuses meaning "no further work". ``completed_at`` is derived from the
#: status instead of being an independent flag, so the two cannot drift apart.
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.DONE})

STATUS_ORDER: tuple[TaskStatus, ...] = (TaskStatus.TODO, TaskStatus.IN_PROGRESS, TaskStatus.DONE)

#: Not alphabetical: "urgent" has to sort above "low". Ordering is spelled out
#: explicitly wherever priority or status is user visible.
PRIORITY_ORDER: tuple[TaskPriority, ...] = (
    TaskPriority.LOW,
    TaskPriority.MEDIUM,
    TaskPriority.HIGH,
    TaskPriority.URGENT,
)


def is_done(status: TaskStatus) -> bool:
    return status in TERMINAL_STATUSES


class Task(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "tasks"

    #: Denormalised from the project so that every tenant-scoped query can filter
    #: on the organization without a join. A project never moves between
    #: organizations, so the copy cannot go stale.
    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
    )
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )

    title: Mapped[str] = mapped_column(String(300), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)

    status: Mapped[TaskStatus] = mapped_column(
        value_enum(TaskStatus, name="task_status", length=16),
        nullable=False,
        default=TaskStatus.TODO,
        server_default=TaskStatus.TODO.value,
    )
    priority: Mapped[TaskPriority] = mapped_column(
        value_enum(TaskPriority, name="task_priority", length=16),
        nullable=False,
        default=TaskPriority.MEDIUM,
        server_default=TaskPriority.MEDIUM.value,
    )

    #: NULL means "nobody is on it", which is a state worth filtering on.
    assignee_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        # SET NULL rather than RESTRICT: losing an account must not block the
        # deletion of work that has already been done.
        ForeignKey("users.id", ondelete="SET NULL"),
    )
    #: Creator, always a member of the same organization.
    creator_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: A deadline is a day, not an instant: "due Friday" is what people mean.
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    comments: Mapped[list[Comment]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="noload",
    )

    __table_args__ = (
        Index("ix_tasks_organization_id", "organization_id"),
        Index("ix_tasks_project_id", "project_id"),
        Index("ix_tasks_assignee_id", "assignee_id"),
        Index("ix_tasks_status", "status"),
        # The list view filters on organization + status and sorts by due date,
        # so those combinations get a composite index rather than two separate
        # ones the planner would have to intersect.
        Index("ix_tasks_organization_id_status_due_date", "organization_id", "status", "due_date"),
        # Substring search uses trigrams, which needs pg_trgm and a GIN index;
        # without them every keystroke would be a sequential scan.
        Index(
            "ix_tasks_title_trgm",
            "title",
            postgresql_using="gin",
            postgresql_ops={"title": GIN_TRGM_OPS},
        ),
        Index(
            "ix_tasks_description_trgm",
            "description",
            postgresql_using="gin",
            postgresql_ops={"description": GIN_TRGM_OPS},
        ),
    )

    def __repr__(self) -> str:
        return f"<Task {self.title!r} {self.status}>"


class Comment(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A message in a task's discussion (docs/architecture.md, section 18)."""

    __tablename__ = "task_comments"

    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    author_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)

    task: Mapped[Task] = relationship(back_populates="comments", lazy="noload")

    __table_args__ = (Index("ix_task_comments_task_id_created_at", "task_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<Comment {self.task_id} by {self.author_id}>"
