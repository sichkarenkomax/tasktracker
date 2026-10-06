"""Task and comment services.

Services own the business rules and publish domain events; routers never touch
the ORM directly (docs/architecture.md, sections 5 and 27). Every event carries
a human-readable ``summary`` and an explicit ``entity_type``/``entity_id``,
because the Activity projector in Core reads only those and never imports this
module (section 19).
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from typing import TYPE_CHECKING, Final
from uuid import UUID

from app.core.errors import ValidationError
from app.core.users.models import User
from app.modules.tasks.models import Comment, Task, TaskPriority, TaskStatus, is_done
from app.modules.tasks.repository import CommentRepository, TaskRepository

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus

TASK_CREATED: Final = "task.created"
TASK_UPDATED: Final = "task.updated"
TASK_STATUS_CHANGED: Final = "task.status_changed"
TASK_PRIORITY_CHANGED: Final = "task.priority_changed"
TASK_ASSIGNED: Final = "task.assigned"
TASK_COMPLETED: Final = "task.completed"
TASK_REOPENED: Final = "task.reopened"
TASK_DELETED: Final = "task.deleted"
COMMENT_CREATED: Final = "comment.created"
COMMENT_DELETED: Final = "comment.deleted"

MAX_COMMENT_LENGTH: Final = 10_000

#: Fields whose movement already produces a dedicated, more specific event. A
#: change confined to these is fully described by that event, so the aggregate
#: ``task.updated`` would only repeat it in the feed.
_DEDICATED_EVENT_FIELDS: Final = frozenset({"status", "priority"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class TaskService:
    def __init__(self, tasks: TaskRepository, bus: EventBus) -> None:
        self._tasks = tasks
        self._bus = bus

    async def create(
        self,
        *,
        organization_id: UUID,
        project_id: UUID | None,
        creator: User,
        title: str,
        description: str | None = None,
        priority: TaskPriority | None = None,
        due_date: date | None = None,
        assignee_id: UUID | None = None,
        status: TaskStatus | None = None,
    ) -> Task:
        chosen_status = status or TaskStatus.TODO
        task = await self._tasks.add(
            Task(
                organization_id=organization_id,
                project_id=project_id,
                title=_clean_title(title),
                description=description,
                status=chosen_status,
                priority=priority or TaskPriority.MEDIUM,
                assignee_id=assignee_id,
                creator_id=creator.id,
                due_date=due_date,
                completed_at=_utcnow() if is_done(chosen_status) else None,
            )
        )

        await self._bus.publish_event(
            TASK_CREATED,
            actor_id=creator.id,
            payload=_task_payload(
                task,
                summary=f"created task {task.title!r}",
                changes={"status": chosen_status.value, "priority": task.priority.value},
            ),
        )
        if task.assignee_id is not None:
            await self._bus.publish_event(
                TASK_ASSIGNED,
                actor_id=creator.id,
                payload=_task_payload(
                    task,
                    summary=f"assigned task {task.title!r} while creating it",
                    changes={"to": str(task.assignee_id)},
                ),
            )
        return task

    async def update(
        self,
        task: Task,
        *,
        actor: User,
        title: str | None = None,
        description: str | None = None,
        description_set: bool = False,
        priority: TaskPriority | None = None,
        due_date: date | None = None,
        due_date_set: bool = False,
        status: TaskStatus | None = None,
        project_id: UUID | None = None,
        project_id_set: bool = False,
    ) -> Task:
        """Apply a partial update, publishing one event per kind of change.

        Events are split by kind rather than collapsed into a single
        ``task.updated`` because section 19 wants the feed to read "Ivan changed
        status: TODO -> IN_PROGRESS", and no future consumer can reconstruct that
        from a generic payload. ``task.updated`` still fires, as the section 20
        contract requires, carrying the list of fields that moved.
        """
        changed: list[str] = []

        if title is not None:
            cleaned = _clean_title(title)
            if cleaned != task.title:
                task.title = cleaned
                changed.append("title")

        # ``description`` and ``due_date`` are nullable, so "not sent" and "sent
        # as null" are different intents; the caller says which one it meant.
        if description_set and description != task.description:
            task.description = description
            changed.append("description")

        # Filing a task under a project, or taking it back out to the inbox, is
        # the same field and the same nullable question.
        if project_id_set and project_id != task.project_id:
            task.project_id = project_id
            changed.append("project")

        if due_date_set and due_date != task.due_date:
            task.due_date = due_date
            changed.append("due_date")

        if priority is not None and priority is not task.priority:
            previous, task.priority = task.priority, priority
            changed.append("priority")
            await self._bus.publish_event(
                TASK_PRIORITY_CHANGED,
                actor_id=actor.id,
                payload=_task_payload(
                    task,
                    summary=(
                        f"changed priority of {task.title!r}: {previous.value} -> {priority.value}"
                    ),
                    changes={"from": previous.value, "to": priority.value},
                ),
            )

        if status is not None and status is not task.status:
            changed.append("status")
            await self._change_status(task, status=status, actor=actor)

        if changed:
            # One line per user action in the feed. ``task.status_changed`` and
            # ``task.priority_changed`` already said what moved and from what to
            # what, so an aggregate row beside them is noise a reader has to read
            # past. The event still fires - a consumer that only wants "something
            # changed" needs exactly one of them - it just does not become a line.
            redundant = set(changed) <= _DEDICATED_EVENT_FIELDS
            await self._bus.publish_event(
                TASK_UPDATED,
                actor_id=actor.id,
                payload=_task_payload(
                    task,
                    # The feed renders one line per event, so an entry without a
                    # summary would be a blank row on the most common action in
                    # the product. The per-kind events above carry the detail;
                    # this one says which fields moved.
                    summary=f"updated {', '.join(changed)} of task {task.title!r}",
                    changes={"fields": changed},
                    skip_activity=redundant,
                ),
            )
        return task

    async def assign(self, task: Task, *, actor: User, assignee_id: UUID | None) -> Task:
        if task.assignee_id == assignee_id:
            return task
        previous, task.assignee_id = task.assignee_id, assignee_id
        await self._bus.publish_event(
            TASK_ASSIGNED,
            actor_id=actor.id,
            payload=_task_payload(
                task,
                summary=(
                    f"assigned task {task.title!r} to {assignee_id}"
                    if assignee_id
                    else f"unassigned task {task.title!r}"
                ),
                changes={
                    "from": str(previous) if previous else None,
                    "to": str(assignee_id) if assignee_id else None,
                },
            ),
        )
        return task

    async def delete(self, task: Task, *, actor: User) -> None:
        payload = _task_payload(task, summary=f"deleted task {task.title!r}")
        await self._tasks.delete(task)
        await self._bus.publish_event(TASK_DELETED, actor_id=actor.id, payload=payload)

    async def _change_status(self, task: Task, *, status: TaskStatus, actor: User) -> None:
        previous, task.status = task.status, status
        was_done, now_done = is_done(previous), is_done(status)
        task.completed_at = _utcnow() if now_done else None

        await self._bus.publish_event(
            TASK_STATUS_CHANGED,
            actor_id=actor.id,
            payload=_task_payload(
                task,
                summary=f"changed status of {task.title!r}: {previous.value} -> {status.value}",
                changes={"from": previous.value, "to": status.value},
            ),
        )

        # Subscribers act on the transition, not on the new value: "became done"
        # and "stopped being done" are different facts
        # (docs/architecture.md, section 21).
        if not was_done and now_done:
            await self._bus.publish_event(
                TASK_COMPLETED,
                actor_id=actor.id,
                payload=_task_payload(task, summary=f"completed task {task.title!r}"),
            )
        elif was_done and not now_done:
            await self._bus.publish_event(
                TASK_REOPENED,
                actor_id=actor.id,
                payload=_task_payload(task, summary=f"reopened task {task.title!r}"),
            )


class CommentService:
    def __init__(self, comments: CommentRepository, bus: EventBus) -> None:
        self._comments = comments
        self._bus = bus

    async def create(self, task: Task, *, author: User, content: str) -> Comment:
        cleaned = content.strip()
        if not cleaned:
            raise ValidationError("Comment must not be blank")
        if len(cleaned) > MAX_COMMENT_LENGTH:
            raise ValidationError(f"Comment must be at most {MAX_COMMENT_LENGTH} characters")

        comment = await self._comments.add(
            Comment(task_id=task.id, author_id=author.id, content=cleaned)
        )
        await self._bus.publish_event(
            COMMENT_CREATED,
            actor_id=author.id,
            payload=_task_payload(
                task,
                summary=f"commented on {task.title!r}",
                changes={"comment_id": str(comment.id)},
            ),
        )
        return comment

    async def delete(self, comment: Comment, *, task: Task, actor: User) -> None:
        await self._comments.delete(comment)
        await self._bus.publish_event(
            COMMENT_DELETED,
            actor_id=actor.id,
            payload=_task_payload(
                task,
                summary=f"deleted a comment on {task.title!r}",
                changes={"comment_id": str(comment.id)},
            ),
        )


def _clean_title(title: str) -> str:
    cleaned = title.strip()
    if not cleaned:
        # A blank title is a client mistake, not a missing field, so it is a 422
        # with a message rather than a database error.
        raise ValidationError("Task title must not be blank")
    return cleaned


def _task_payload(task: Task, *, summary: str | None = None, **extra: object) -> dict[str, object]:
    """Envelope every Tasks event shares.

    ``entity_type``/``entity_id`` are set explicitly rather than left to the
    projector's name-based guesswork, so a comment row in the feed still points
    at the task it belongs to.
    """
    payload: dict[str, object] = {
        "task_id": str(task.id),
        "project_id": str(task.project_id),
        "organization_id": str(task.organization_id),
        "title": task.title,
        "entity_type": "task",
        "entity_id": str(task.id),
    }
    if summary is not None:
        payload["summary"] = summary
    payload.update(extra)
    return payload
