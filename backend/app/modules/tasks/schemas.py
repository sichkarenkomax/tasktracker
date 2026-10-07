"""Pydantic schemas for tasks and comments."""

from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.modules.tasks.models import DurationUnit, ParticipantRole, TaskPriority, TaskStatus
from app.modules.tasks.repository import DEFAULT_SORT, SORTABLE


#: Unknown fields are rejected rather than dropped. Pydantic's default is to
#: ignore them, which turns a typo - or a client assuming ``status`` may be set
#: on create - into a request that reports success and quietly does nothing. The
#: same reasoning that rejects an unknown ``?sort=`` applies to the body.
class WriteModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class PlanningFields(WriteModel):
    """The planned window, shared by create and update.

    On update every field needs a sentinel for the same reason ``due_date`` does:
    omitting the key must mean "leave it alone", and only an explicit ``null``
    clears the plan.
    """

    planned_start: datetime | None = None
    planned_end: datetime | None = None
    planned_duration: int | None = Field(default=None, ge=0)
    duration_unit: DurationUnit | None = None


class TaskCreate(PlanningFields):
    title: str = Field(min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    priority: TaskPriority | None = None
    due_date: date | None = None
    #: Optional on the wire even though the column is not: a client that omits it
    #: gets the creator, which is the only sensible default for "whose work is
    #: this" at the moment it is written down.
    assignee_id: UUID | None = None
    #: Only meaningful on the flat ``POST /tasks``. The nested route takes the
    #: project from its path, so sending it there is a 422 rather than a value
    #: that silently disagrees with the URL.
    project_id: UUID | None = None


class TaskUpdate(PlanningFields):
    """Every field is optional; omitted means "leave as it is".

    ``due_date`` needs the sentinel: sending ``null`` must clear the deadline,
    while omitting the key must not. ``model_fields_set`` carries that
    distinction from the router into the service.
    """

    title: str | None = Field(default=None, min_length=1, max_length=300)
    description: str | None = Field(default=None, max_length=20_000)
    priority: TaskPriority | None = None
    due_date: date | None = None
    #: Null is refused rather than honoured - see the comment in ``assign``.
    assignee_id: UUID | None = None
    status: TaskStatus | None = None
    #: Lets a task be filed under a project, or moved to another one, without a
    #: separate endpoint. ``null`` takes it back out to the inbox.
    project_id: UUID | None = None


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    #: ``None`` means the task is not filed under a project.
    project_id: UUID | None
    title: str
    description: str | None
    status: TaskStatus
    priority: TaskPriority
    assignee_id: UUID
    creator_id: UUID
    due_date: date | None
    completed_at: datetime | None
    planned_start: datetime | None
    planned_end: datetime | None
    planned_duration: int | None
    duration_unit: DurationUnit
    created_at: datetime
    updated_at: datetime


class TaskPage(BaseModel):
    """Envelope matching the Activity feed, so the SPA handles one shape."""

    items: list[TaskRead]
    total: int
    limit: int
    offset: int
    sort: str
    direction: str


class CommentCreate(WriteModel):
    content: str = Field(min_length=1, max_length=10_000)


class CommentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    task_id: UUID
    author_id: UUID
    content: str
    created_at: datetime
    updated_at: datetime


class CommentPage(BaseModel):
    items: list[CommentRead]
    total: int
    limit: int
    offset: int


class ParticipantRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    task_id: UUID
    user_id: UUID
    role: ParticipantRole
    created_at: datetime


class ParticipantAdd(WriteModel):
    user_id: UUID
    role: ParticipantRole


#: Exposed so the API layer can reject an unknown sort field with 422 instead of
#: silently falling back - a silently ignored `?sort=priorty` is a bug report
#: nobody can reproduce.
SORT_FIELDS: frozenset[str] = SORTABLE
DEFAULT_SORT_FIELD: str = DEFAULT_SORT
