"""Task and Comment models.

Tasks is the first functional module, and the only place besides Core that owns
tables (docs/architecture.md, sections 13, 14, 18). Nothing here is imported by
Core: the module reaches the platform through services, permissions and the event
bus only, which is what keeps the boundary in section 64 intact.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from enum import StrEnum
from uuid import UUID

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
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

    ``DEFERRED`` is the fourth: work that is deliberately parked rather than
    started. It is deliberately *not* terminal - a deferred task still counts as
    open work, so it can still be overdue, and reopening it is a status change
    like any other. Folding "postponed" into "todo" would lose the distinction
    between "not started" and "deliberately not now", which is the only reason to
    record it.
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    DEFERRED = "deferred"
    DONE = "done"


class TaskPriority(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    URGENT = "urgent"


class ParticipantRole(StrEnum):
    """How somebody is attached to a task beyond being responsible for it."""

    #: Doing the work alongside the assignee.
    CO_ASSIGNEE = "co_assignee"
    #: Kept informed, doing nothing.
    WATCHER = "watcher"


class DurationUnit(StrEnum):
    """The unit a planned duration is counted in.

    Minutes are there because estimating a support answer in hours is useless.
    Months are there because a roadmap is written in them. Both are calendar
    aware - adding one month to 31 January gives 28 or 29 February, not 31
    February - which is why the arithmetic lives in the service and not in SQL.
    """

    MINUTES = "minutes"
    HOURS = "hours"
    DAYS = "days"
    WEEKS = "weeks"
    MONTHS = "months"


#: Statuses meaning "no further work". ``completed_at`` is derived from the
#: status instead of being an independent flag, so the two cannot drift apart.
TERMINAL_STATUSES: frozenset[TaskStatus] = frozenset({TaskStatus.DONE})

#: The order statuses are offered and ranked in. Spelled out rather than derived
#: from the enum: "todo, in progress, deferred, done" is a workflow, not an
#: alphabetical accident.
STATUS_ORDER: tuple[TaskStatus, ...] = (
    TaskStatus.TODO,
    TaskStatus.IN_PROGRESS,
    TaskStatus.DEFERRED,
    TaskStatus.DONE,
)

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


def add_duration(
    start: datetime,
    amount: int,
    unit: DurationUnit,
) -> datetime:
    """``start`` plus ``amount`` units, calendar-aware.

    Months and years are not fixed lengths, so this clamps rather than overflowing:
    one month after 31 January is the last day of February, not 3 March. The
    alternative - 30 days per month - drifts a roadmap by a fortnight a year, which
    is exactly the kind of error nobody notices until it is expensive.

    Python's ``timedelta`` does the fixed units; ``dateutil`` is not a dependency
    here, and calendar months are the only non-fixed case.
    """
    if amount == 0:
        return start

    if unit is DurationUnit.MINUTES:
        return start + timedelta(minutes=amount)
    if unit is DurationUnit.HOURS:
        return start + timedelta(hours=amount)
    if unit is DurationUnit.DAYS:
        return start + timedelta(days=amount)
    if unit is DurationUnit.WEEKS:
        return start + timedelta(weeks=amount)

    # Months.
    total = start.month - 1 + amount
    year = start.year + total // 12
    month = total % 12 + 1
    day = min(start.day, _days_in_month(year, month))
    return start.replace(year=year, month=month, day=day)


def _days_in_month(year: int, month: int) -> int:
    if month == 12:
        return 31
    return (date(year, month + 1, 1) - timedelta(days=1)).day


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
    #: NULL means the task is not filed under a project. Section 30 wants a task
    #: list that is not a project list, and the inbox this product opens with -
    #: "what do I have to do" - cannot answer that if every task must be filed
    #: first. The organization is still required, so tenant isolation does not
    #: depend on the project.
    project_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("projects.id", ondelete="CASCADE"),
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

    #: The person answerable for the work. Mandatory: a task with nobody on it is
    #: work that silently does not happen, and "who is this for" is not a question
    #: a task list should be able to answer with "nobody". The migration filled
    #: existing rows with the creator, so nothing became invalid.
    assignee_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        # RESTRICT rather than SET NULL: losing an account must not be able to
        # leave a task with no responsible person, which the column forbids.
        ForeignKey("users.id", ondelete="RESTRICT"),
    )
    #: Creator, always a member of the same organization. Distinct from the
    #: assignee: somebody can report work they are not doing.
    creator_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )

    #: A deadline is an instant, not a day.
    #:
    #: It was a `Date` while the only calendar in the product was the browser's,
    #: which cannot even be themed. Now that the deadline carries a time of day
    #: ("hand it in by 18:00"), "overdue" has to mean "the moment passed" and the
    #: column has to hold that moment. Rows written before the change become
    #: midnight UTC on their old day, which is the only reading a bare date had.
    due_date: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    #: --- planning --------------------------------------------------------------
    #: The planned window, as instants rather than dates.
    #:
    #: A single deadline column was not enough. Planning a two-week job inside one
    #: date means the end is computed on every read, and the start has nowhere to
    #: live at all. Storing the window keeps "when does this begin and when is it
    #: meant to be finished" answerable by an index rather than by arithmetic in a
    #: template.
    planned_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    planned_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: How long the work is meant to take, as a number of ``duration_unit``s from
    #: ``planned_start``. A pair rather than one interval column because "three
    #: days" and "three months" are both durations a planner actually writes down,
    #: and neither survives being stored as a single number without the unit.
    planned_duration: Mapped[int | None] = mapped_column(Integer)
    duration_unit: Mapped[DurationUnit] = mapped_column(
        value_enum(DurationUnit, name="duration_unit", length=16),
        default=DurationUnit.HOURS,
        server_default=DurationUnit.HOURS.value,
    )

    comments: Mapped[list[Comment]] = relationship(
        back_populates="task",
        cascade="all, delete-orphan",
        lazy="noload",
    )
    participants: Mapped[list[TaskParticipant]] = relationship(
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
        # The inbox - "tasks of this organization with no project" - is what every
        # page load asks for once project_id is nullable. A plain b-tree on a
        # column that is NULL for all of those rows would be mostly dead weight,
        # so the index only covers them.
        Index(
            "ix_tasks_organization_id_unfiled",
            "organization_id",
            postgresql_where=text("project_id IS NULL"),
        ),
        # The planned window is what a Gantt and a calendar read, both of which
        # filter by start and order by end.
        Index("ix_tasks_organization_id_planned_start", "organization_id", "planned_start"),
        Index("ix_tasks_planned_end", "planned_end"),
    )

    def __repr__(self) -> str:
        return f"<Task {self.title!r} {self.status}>"


class TaskParticipant(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """Somebody attached to a task, in a capacity other than being on it.

    Two roles, one table. A join table with an enum column rather than two tables
    because the two behave identically - add, remove, list, authorize the same way
    - and two tables would mean every query and every endpoint written twice. The
    reporter is deliberately *not* here: it is the creator, already on the task.

    Assignment and comment rights are unchanged by this table. Being a
    co-assignee is a statement about who is doing the work; it does not grant the
    right to comment, which stays with the role. Otherwise anybody could hand out
    comment rights by adding a name.
    """

    __tablename__ = "task_participants"

    task_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("tasks.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    role: Mapped[ParticipantRole] = mapped_column(
        value_enum(ParticipantRole, name="task_participant_role", length=16),
        nullable=False,
    )

    task: Mapped[Task] = relationship(back_populates="participants", lazy="noload")

    __table_args__ = (
        # One row per (task, user, role): the same person cannot be added twice,
        # and the unique index is what makes the insert fail rather than the
        # application having to check first.
        UniqueConstraint("task_id", "user_id", "role", name="uq_task_participants_task_user_role"),
        Index("ix_task_participants_task_id", "task_id"),
        Index("ix_task_participants_user_id", "user_id"),
    )

    def __repr__(self) -> str:
        return f"<TaskParticipant {self.user_id} {self.role}>"


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
