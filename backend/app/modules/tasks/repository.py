"""Repositories for tasks and comments.

Every query is scoped by ``organization_id``: the tenant boundary is enforced in
the data layer, not only in the API layer, so a forgotten check upstream cannot
leak another organization's work (docs/architecture.md, section 10).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Final, cast
from uuid import UUID

from sqlalchemy import ColumnElement, Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import InstrumentedAttribute

from app.database.helpers import count, fetch_all, fetch_one
from app.modules.tasks.models import (
    PRIORITY_ORDER,
    STATUS_ORDER,
    TERMINAL_STATUSES,
    Comment,
    ParticipantRole,
    Task,
    TaskParticipant,
    TaskPriority,
    TaskStatus,
)

#: Columns a client may sort by. Anything not in here is rejected rather than
#: interpolated into ORDER BY: the sort field arrives as a query string and must
#: never be able to reach the SQL text.
SORTABLE: Final[frozenset[str]] = frozenset(
    {"created_at", "updated_at", "due_date", "title", "priority", "status"}
)
DEFAULT_SORT: Final = "created_at"


@dataclass(frozen=True, slots=True)
class TaskFilters:
    """Every list query is described by this object, so filtering and counting
    can never disagree about which rows are in scope."""

    organization_id: UUID
    project_id: UUID | None = None
    status: tuple[TaskStatus, ...] = ()
    priority: tuple[TaskPriority, ...] = ()
    assignee_id: UUID | None = None
    #: Only tasks not filed under any project - the inbox as its own view.
    unfiled: bool = False
    creator_id: UUID | None = None
    due_from: datetime | None = None
    due_to: datetime | None = None
    overdue: bool = False
    search: str | None = None
    #: "Now" for the overdue test, injectable so a test can say what time it is.
    #: Aware and in UTC, because the column is: comparing an aware value with a
    #: naive one would either raise or silently read as the database's zone.
    now: datetime = field(default_factory=lambda: datetime.now(UTC))

    def conditions(self) -> list[ColumnElement[bool]]:
        clauses: list[ColumnElement[bool]] = [Task.organization_id == self.organization_id]
        if self.project_id is not None:
            clauses.append(Task.project_id == self.project_id)
        if self.status:
            clauses.append(Task.status.in_(self.status))
        if self.priority:
            clauses.append(Task.priority.in_(self.priority))
        if self.assignee_id is not None:
            clauses.append(Task.assignee_id == self.assignee_id)
        if self.unfiled:
            clauses.append(Task.project_id.is_(None))
        if self.creator_id is not None:
            clauses.append(Task.creator_id == self.creator_id)
        if self.due_from is not None:
            clauses.append(Task.due_date >= self.due_from)
        if self.due_to is not None:
            clauses.append(Task.due_date <= self.due_to)
        if self.overdue:
            # Overdue means "the deadline passed and the task is still open"; a
            # closed task can never be overdue no matter how old it is. With the
            # deadline an instant, a task due later today at 18:00 is not overdue
            # at 10:00 - which is the whole reason the column grew a time.
            clauses.append(Task.due_date < self.now)
            clauses.append(Task.status.notin_(tuple(TERMINAL_STATUSES)))
        if self.search:
            clauses.extend(_search_conditions(self.search))
        return clauses


def _search_conditions(search: str) -> list[ColumnElement[bool]]:
    """Match every whitespace-separated token against title or description.

    ``ILIKE`` is deliberate over a full-text vector: users expect a substring,
    not a stemmed word, and trigram indexes (created in the migration) make the
    pattern match an index lookup instead of a sequential scan
    (docs/architecture.md, section 42).
    """
    tokens = [token for token in search.split() if token]
    if not tokens:
        return []
    return [
        or_(
            Task.title.ilike(_pattern(token), escape="\\"),
            Task.description.ilike(_pattern(token), escape="\\"),
        )
        for token in tokens
    ]


def _pattern(token: str) -> str:
    """Wildcard-escape user input before it reaches a LIKE pattern."""
    escaped = token.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _enum_rank(column: InstrumentedAttribute[Any], order: tuple[Any, ...]) -> ColumnElement[int]:
    """Rank an enum column by its declared progression rather than alphabetically."""
    return case(
        *((column == value, rank) for rank, value in enumerate(order)),
        else_=len(order),
    )


def sort_expression(sort: str, descending: bool) -> tuple[Any, ...]:
    """Build the ORDER BY terms for an already validated `sort` field.

    A stable tie-breaker on ``id`` is mandatory: without it, two rows that tie on
    the sort column can swap places between pages, and one of them is then served
    twice while another never appears at all.
    """
    column: ColumnElement[Any]
    match sort:
        case "priority":
            column = _enum_rank(Task.priority, PRIORITY_ORDER)
        case "status":
            column = _enum_rank(Task.status, STATUS_ORDER)
        case "due_date":
            # Tasks without a deadline always sink, whichever way the user sorted:
            # an empty cell at the top of a due-date list is noise, not urgency.
            due_date = cast("ColumnElement[Any]", Task.due_date)
            term = due_date.desc().nulls_last() if descending else due_date.asc().nulls_last()
            return (term, Task.id)
        case _:
            column = cast("ColumnElement[Any]", getattr(Task, sort))

    return (column.desc() if descending else column.asc(), Task.id)


class TaskRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, task_id: UUID, *, organization_id: UUID) -> Task | None:
        return await fetch_one(
            self._session,
            select(Task).where(Task.id == task_id, Task.organization_id == organization_id),
        )

    async def count(self, filters: TaskFilters) -> int:
        statement = select(func.count()).select_from(Task).where(*filters.conditions())
        return await count(self._session, statement)

    async def list(
        self,
        filters: TaskFilters,
        *,
        sort: str = DEFAULT_SORT,
        descending: bool = False,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Task]:
        statement: Select[tuple[Task]] = (
            select(Task)
            .where(and_(*filters.conditions()))
            .order_by(*sort_expression(sort, descending))
        )
        return await fetch_all(self._session, statement.limit(limit).offset(offset))

    async def comment_count(self, task_id: UUID) -> int:
        statement = select(func.count()).select_from(Comment).where(Comment.task_id == task_id)
        return await count(self._session, statement)

    async def add(self, task: Task) -> Task:
        self._session.add(task)
        await self._session.flush()
        return task

    async def delete(self, task: Task) -> None:
        await self._session.delete(task)
        await self._session.flush()


class CommentRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, comment_id: UUID, *, task_id: UUID) -> Comment | None:
        return await fetch_one(
            self._session,
            select(Comment).where(Comment.id == comment_id, Comment.task_id == task_id),
        )

    async def list_for_task(
        self, task_id: UUID, *, limit: int = 100, offset: int = 0
    ) -> list[Comment]:
        statement = (
            select(Comment)
            .where(Comment.task_id == task_id)
            .order_by(Comment.created_at, Comment.id)
            .limit(limit)
            .offset(offset)
        )
        return await fetch_all(self._session, statement)

    async def count_for_task(self, task_id: UUID) -> int:
        statement = select(func.count()).select_from(Comment).where(Comment.task_id == task_id)
        return await count(self._session, statement)

    async def add(self, comment: Comment) -> Comment:
        self._session.add(comment)
        await self._session.flush()
        return comment

    async def delete(self, comment: Comment) -> None:
        await self._session.delete(comment)
        await self._session.flush()


class ParticipantRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list(self, task_id: UUID) -> list[TaskParticipant]:
        statement = (
            select(TaskParticipant)
            .where(TaskParticipant.task_id == task_id)
            # Co-assignees first, then watchers, each alphabetical: the list is
            # read as two groups, and an unstable order would make it shuffle.
            .order_by(TaskParticipant.role, TaskParticipant.user_id)
        )
        return await fetch_all(self._session, statement)

    async def get(
        self, task_id: UUID, *, user_id: UUID, role: ParticipantRole
    ) -> TaskParticipant | None:
        return await fetch_one(
            self._session,
            select(TaskParticipant).where(
                TaskParticipant.task_id == task_id,
                TaskParticipant.user_id == user_id,
                TaskParticipant.role == role,
            ),
        )

    async def add(self, participant: TaskParticipant) -> TaskParticipant:
        self._session.add(participant)
        await self._session.flush()
        return participant

    async def remove(self, task_id: UUID, *, user_id: UUID, role: ParticipantRole) -> bool:
        participant = await self.get(task_id, user_id=user_id, role=role)
        if participant is None:
            return False
        await self._session.delete(participant)
        await self._session.flush()
        return True
