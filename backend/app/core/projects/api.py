"""Project API.

Routes are addressed by project id; the organization context travels as a query
parameter so that a single project id is enough to identify a resource
(docs/architecture.md, section 26). Permission checks still run inside the
organization, so tenant isolation is unaffected.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, status

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.dependencies import EventBusDep
from app.core.errors import NotFoundError
from app.core.permissions.service import AuthorizationService
from app.core.projects.models import Project
from app.core.projects.repository import ProjectRepository
from app.core.projects.schemas import ProjectCreate, ProjectRead, ProjectUpdate
from app.core.projects.service import ProjectService
from app.core.users.models import User

router = APIRouter(prefix="/projects", tags=["projects"])


async def _authorize(
    session: SessionDep, user: User, organization_id: UUID, permission: str
) -> None:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission=permission
    )


async def _load(session: SessionDep, project_id: UUID, organization_id: UUID) -> Project:
    project = await ProjectRepository(session).get(project_id, organization_id=organization_id)
    if project is None:
        raise NotFoundError("Project not found")
    return project


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(
    payload: ProjectCreate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> ProjectRead:
    await _authorize(session, user, payload.organization_id, "project.create")
    project = await ProjectService(ProjectRepository(session), bus).create(
        organization_id=payload.organization_id,
        owner=user,
        name=payload.name,
        description=payload.description,
    )
    await session.commit()
    return ProjectRead.model_validate(project)


@router.get("", response_model=list[ProjectRead])
async def list_projects(
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> list[ProjectRead]:
    await _authorize(session, user, organization_id, "project.view")
    projects = await ProjectRepository(session).list_for_organization(organization_id)
    return [ProjectRead.model_validate(project) for project in projects]


@router.get("/{project_id}", response_model=ProjectRead)
async def read_project(
    project_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> ProjectRead:
    await _authorize(session, user, organization_id, "project.view")
    return ProjectRead.model_validate(await _load(session, project_id, organization_id))


@router.patch("/{project_id}", response_model=ProjectRead)
async def update_project(
    project_id: UUID,
    organization_id: UUID,
    payload: ProjectUpdate,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> ProjectRead:
    await _authorize(session, user, organization_id, "project.update")
    project = await _load(session, project_id, organization_id)
    updated = await ProjectService(ProjectRepository(session), bus).update(
        project,
        actor=user,
        name=payload.name,
        description=payload.description,
        status=payload.status,
    )
    await session.commit()
    return ProjectRead.model_validate(updated)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(
    project_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await _authorize(session, user, organization_id, "project.delete")
    project = await _load(session, project_id, organization_id)
    await ProjectService(ProjectRepository(session), bus).delete(project, actor=user)
    await session.commit()
