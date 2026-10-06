"""Tasks API.

Two shapes over one implementation:

* ``/tasks`` and ``/tasks/{id}`` address a task by its own id;
* ``/projects/{project_id}/tasks`` is the nested form the REST sketch in
  section 26 asks for.

Both carry ``organization_id`` as a query parameter rather than in the path,
because a task already belongs to a project and a project to an organization.
The authorization check still runs inside that organization, so tenant isolation
is unaffected - the same trade-off Core's project routes make.
"""

from __future__ import annotations

from datetime import date
from uuid import UUID

from fastapi import APIRouter, Query, status

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.dependencies import EventBusDep
from app.core.errors import NotFoundError, ValidationError
from app.core.organizations.repository import OrganizationRepository
from app.core.pagination import PageDep, PageParams
from app.core.permissions.service import AuthorizationService
from app.core.projects.models import Project
from app.core.projects.repository import ProjectRepository
from app.core.users.models import User
from app.modules.tasks import permissions as task_permissions
from app.modules.tasks.models import Task, TaskPriority, TaskStatus, is_done
from app.modules.tasks.repository import (
    DEFAULT_SORT,
    SORTABLE,
    CommentRepository,
    TaskFilters,
    TaskRepository,
)
from app.modules.tasks.schemas import (
    CommentCreate,
    CommentPage,
    CommentRead,
    TaskCreate,
    TaskPage,
    TaskRead,
    TaskUpdate,
)
from app.modules.tasks.service import CommentService, TaskService

router = APIRouter(tags=["tasks"])

#: An unknown sort field is rejected by pattern instead of reaching ORDER BY:
#: the value arrives in a query string and must never be interpolated into SQL.
SORT_PATTERN = rf"^({'|'.join(sorted(SORTABLE))})$"
DIRECTION_PATTERN = r"^(asc|desc)$"


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _authorize(
    session: SessionDep, user: User, organization_id: UUID, permission: str
) -> None:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission=permission
    )


async def _load_task(session: SessionDep, task_id: UUID, organization_id: UUID) -> Task:
    task = await TaskRepository(session).get(task_id, organization_id=organization_id)
    if task is None:
        raise NotFoundError("Task not found")
    return task


async def _load_project(session: SessionDep, project_id: UUID, organization_id: UUID) -> Project:
    project = await ProjectRepository(session).get(project_id, organization_id=organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


async def _validate_assignee(
    session: SessionDep, organization_id: UUID, assignee_id: UUID | None
) -> None:
    """Work can only be handed to somebody inside the tenant.

    422 rather than 403: the caller *is* allowed to assign, the value they passed
    is simply not usable.
    """
    if assignee_id is None:
        return
    member = await OrganizationRepository(session).get_member(
        organization_id=organization_id, user_id=assignee_id
    )
    if member is None:
        raise ValidationError(
            "Assignee must be a member of the organization",
            details={"assignee_id": str(assignee_id)},
        )


def _filters(
    *,
    organization_id: UUID,
    project_id: UUID | None = None,
    status: list[TaskStatus] | None = None,
    priority: list[TaskPriority] | None = None,
    assignee_id: UUID | None = None,
    unassigned: bool = False,
    unfiled: bool = False,
    creator_id: UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue: bool = False,
    search: str | None = None,
) -> TaskFilters:
    return TaskFilters(
        organization_id=organization_id,
        project_id=project_id,
        status=tuple(status or ()),
        priority=tuple(priority or ()),
        assignee_id=assignee_id,
        unassigned=unassigned,
        unfiled=unfiled,
        creator_id=creator_id,
        due_from=due_from,
        due_to=due_to,
        overdue=overdue,
        search=search,
    )


async def _page(
    session: SessionDep, filters: TaskFilters, page: PageParams, sort: str, direction: str
) -> TaskPage:
    """Count and slice with the same filters, so ``total`` always matches ``items``."""
    repository = TaskRepository(session)
    total = await repository.count(filters)
    tasks = await repository.list(
        filters,
        sort=sort,
        descending=direction == "desc",
        limit=page.limit,
        offset=page.offset,
    )
    return TaskPage(
        items=[TaskRead.model_validate(task) for task in tasks],
        total=total,
        limit=page.limit,
        offset=page.offset,
        sort=sort,
        direction=direction,
    )


# ---------------------------------------------------------------------------
# collections
# ---------------------------------------------------------------------------


@router.get("/tasks", response_model=TaskPage, summary="List tasks of an organization")
async def list_tasks(
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
    project_id: UUID | None = None,
    status_: list[TaskStatus] | None = Query(default=None, alias="status"),
    priority: list[TaskPriority] | None = Query(default=None),
    assignee_id: UUID | None = None,
    unassigned: bool = False,
    unfiled: bool = False,
    creator_id: UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue: bool = False,
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default=DEFAULT_SORT, pattern=SORT_PATTERN),
    direction: str = Query(default="desc", pattern=DIRECTION_PATTERN),
) -> TaskPage:
    await _authorize(session, user, organization_id, task_permissions.VIEW)
    return await _page(
        session,
        _filters(
            organization_id=organization_id,
            project_id=project_id,
            status=status_,
            priority=priority,
            assignee_id=assignee_id,
            unassigned=unassigned,
            unfiled=unfiled,
            creator_id=creator_id,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            search=search,
        ),
        page,
        sort,
        direction,
    )


@router.post(
    "/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task, optionally filed under a project",
)
async def create_task(
    organization_id: UUID,
    payload: TaskCreate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> TaskRead:
    """The flat form of create, for a task that belongs to the organization but to
    no project yet.

    Section 30 lists the task list as the home screen, and an inbox nobody can put
    anything into until they have first created a project is not an inbox.
    ``project_id`` is optional here; when it is given it is validated exactly as
    the nested route validates it, so the flat form is not a way around tenant
    isolation.
    """
    await _authorize(session, user, organization_id, task_permissions.CREATE)
    project_id = payload.project_id
    if project_id is not None:
        await _load_project(session, project_id, organization_id)
    await _validate_assignee(session, organization_id, payload.assignee_id)
    task = await TaskService(TaskRepository(session), bus).create(
        organization_id=organization_id,
        project_id=project_id,
        creator=user,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
        assignee_id=payload.assignee_id,
    )
    await session.commit()
    return TaskRead.model_validate(task)


@router.get(
    "/projects/{project_id}/tasks",
    response_model=TaskPage,
    summary="List the tasks of one project",
)
async def list_project_tasks(
    project_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
    status_: list[TaskStatus] | None = Query(default=None, alias="status"),
    priority: list[TaskPriority] | None = Query(default=None),
    assignee_id: UUID | None = None,
    unassigned: bool = False,
    creator_id: UUID | None = None,
    due_from: date | None = None,
    due_to: date | None = None,
    overdue: bool = False,
    search: str | None = Query(default=None, max_length=200),
    sort: str = Query(default=DEFAULT_SORT, pattern=SORT_PATTERN),
    direction: str = Query(default="desc", pattern=DIRECTION_PATTERN),
) -> TaskPage:
    # 404 before 403: a project id from another tenant must be
    # indistinguishable from one that does not exist.
    await _load_project(session, project_id, organization_id)
    await _authorize(session, user, organization_id, task_permissions.VIEW)
    # The same filter set as ``/tasks``: the project id narrows the scope, it
    # must not silently drop the deadline range a backlog view needs.
    return await _page(
        session,
        _filters(
            organization_id=organization_id,
            project_id=project_id,
            status=status_,
            priority=priority,
            assignee_id=assignee_id,
            unassigned=unassigned,
            creator_id=creator_id,
            due_from=due_from,
            due_to=due_to,
            overdue=overdue,
            search=search,
        ),
        page,
        sort,
        direction,
    )


@router.post(
    "/projects/{project_id}/tasks",
    response_model=TaskRead,
    status_code=status.HTTP_201_CREATED,
    summary="Create a task in a project",
)
async def create_project_task(
    project_id: UUID,
    organization_id: UUID,
    payload: TaskCreate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> TaskRead:
    project = await _load_project(session, project_id, organization_id)
    await _authorize(session, user, organization_id, task_permissions.CREATE)
    await _validate_assignee(session, organization_id, payload.assignee_id)
    if payload.project_id is not None and payload.project_id != project.id:
        # The path is the authority here. Accepting a body that disagrees would
        # mean two sources of truth for one field, and the loser would be
        # whichever the caller was not looking at.
        raise ValidationError(
            "project_id is taken from the path; remove it from the body",
            details={"field": "project_id"},
        )

    task = await TaskService(TaskRepository(session), bus).create(
        organization_id=project.organization_id,
        project_id=project.id,
        creator=user,
        title=payload.title,
        description=payload.description,
        priority=payload.priority,
        due_date=payload.due_date,
        assignee_id=payload.assignee_id,
    )
    await session.commit()
    return TaskRead.model_validate(task)


# ---------------------------------------------------------------------------
# single task
# ---------------------------------------------------------------------------


@router.get("/tasks/{task_id}", response_model=TaskRead, summary="Read one task")
async def read_task(
    task_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> TaskRead:
    await _authorize(session, user, organization_id, task_permissions.VIEW)
    return TaskRead.model_validate(await _load_task(session, task_id, organization_id))


@router.patch("/tasks/{task_id}", response_model=TaskRead, summary="Update a task")
async def update_task(
    task_id: UUID,
    organization_id: UUID,
    payload: TaskUpdate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> TaskRead:
    await _authorize(session, user, organization_id, task_permissions.UPDATE)
    task = await _load_task(session, task_id, organization_id)

    # Closing and reopening is a distinct privilege from editing a task: "done"
    # is what reporting is built on, so a role that may edit but not complete has
    # to be expressible (section 25).
    crosses_completion = (
        payload.status is not None
        and payload.status is not task.status
        and is_done(payload.status) != is_done(task.status)
    )
    if crosses_completion:
        await _authorize(session, user, organization_id, task_permissions.COMPLETE)

    reassigning = "assignee_id" in payload.model_fields_set
    if reassigning:
        await _authorize(session, user, organization_id, task_permissions.ASSIGN)
        await _validate_assignee(session, organization_id, payload.assignee_id)

    # Moving a task between projects needs the same right as editing it, but the
    # target project has to exist inside this organization - otherwise a task
    # could be filed into another tenant's project by guessing its id.
    refiling = "project_id" in payload.model_fields_set
    if refiling and payload.project_id is not None:
        await _load_project(session, payload.project_id, organization_id)

    service = TaskService(TaskRepository(session), bus)
    if reassigning:
        await service.assign(task, actor=user, assignee_id=payload.assignee_id)
    updated = await service.update(
        task,
        actor=user,
        title=payload.title,
        description=payload.description,
        description_set="description" in payload.model_fields_set,
        priority=payload.priority,
        due_date=payload.due_date,
        due_date_set="due_date" in payload.model_fields_set,
        status=payload.status,
        project_id=payload.project_id,
        project_id_set=refiling,
    )
    await session.commit()
    return TaskRead.model_validate(updated)


@router.delete("/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a task")
async def delete_task(
    task_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await _authorize(session, user, organization_id, task_permissions.DELETE)
    task = await _load_task(session, task_id, organization_id)
    await TaskService(TaskRepository(session), bus).delete(task, actor=user)
    await session.commit()


# ---------------------------------------------------------------------------
# comments
# ---------------------------------------------------------------------------


@router.get(
    "/tasks/{task_id}/comments",
    response_model=CommentPage,
    summary="List the comments of a task",
)
async def list_comments(
    task_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    page: PageDep,
) -> CommentPage:
    await _authorize(session, user, organization_id, task_permissions.VIEW)
    await _load_task(session, task_id, organization_id)
    repository = CommentRepository(session)
    total = await repository.count_for_task(task_id)
    comments = await repository.list_for_task(task_id, limit=page.limit, offset=page.offset)
    return CommentPage(
        items=[CommentRead.model_validate(comment) for comment in comments],
        total=total,
        limit=page.limit,
        offset=page.offset,
    )


@router.post(
    "/tasks/{task_id}/comments",
    response_model=CommentRead,
    status_code=status.HTTP_201_CREATED,
    summary="Comment on a task",
)
async def create_comment(
    task_id: UUID,
    organization_id: UUID,
    payload: CommentCreate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> CommentRead:
    await _authorize(session, user, organization_id, task_permissions.COMMENT_CREATE)
    task = await _load_task(session, task_id, organization_id)
    comment = await CommentService(CommentRepository(session), bus).create(
        task, author=user, content=payload.content
    )
    await session.commit()
    return CommentRead.model_validate(comment)


@router.delete(
    "/tasks/{task_id}/comments/{comment_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a comment",
)
async def delete_comment(
    task_id: UUID,
    comment_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await _authorize(session, user, organization_id, task_permissions.COMMENT_CREATE)
    task = await _load_task(session, task_id, organization_id)
    comment = await CommentRepository(session).get(comment_id, task_id=task_id)
    if comment is None:
        raise NotFoundError("Comment not found")
    # A comment belongs to whoever wrote it. Anybody else may remove it only with
    # the same privilege that removes the whole task, which keeps moderation
    # with the roles that already have `task.delete`.
    if comment.author_id != user.id:
        await _authorize(session, user, organization_id, task_permissions.DELETE)
    await CommentService(CommentRepository(session), bus).delete(comment, task=task, actor=user)
    await session.commit()


#: Picked up by module discovery (see app/core/modules/registry.py).
API_ROUTER = router

__all__ = ["API_ROUTER", "router"]
