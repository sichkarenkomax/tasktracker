"""Project service."""

from __future__ import annotations

from typing import TYPE_CHECKING
from uuid import UUID

from app.core.errors import ConflictError, NotFoundError
from app.core.events.names import (
    PROJECT_CREATED,
    PROJECT_DELETED,
    PROJECT_UPDATED,
)
from app.core.projects.models import Project, ProjectStatus
from app.core.projects.repository import ProjectRepository
from app.core.users.models import User

if TYPE_CHECKING:  # pragma: no cover
    from app.core.events.bus import EventBus


class ProjectService:
    def __init__(self, projects: ProjectRepository, bus: EventBus) -> None:
        self._projects = projects
        self._bus = bus

    async def create(
        self,
        *,
        organization_id: UUID,
        owner: User,
        name: str,
        description: str | None = None,
    ) -> Project:
        if await self._projects.name_taken(organization_id, name):
            raise ConflictError(f"A project named '{name}' already exists in this organization")

        project = await self._projects.add(
            Project(
                organization_id=organization_id,
                name=name,
                description=description,
                owner_id=owner.id,
            )
        )
        await self._bus.publish_event(
            PROJECT_CREATED,
            actor_id=owner.id,
            payload={
                "project_id": str(project.id),
                "organization_id": str(organization_id),
                "name": project.name,
                "summary": f"created project {project.name!r}",
            },
        )
        return project

    async def update(
        self,
        project: Project,
        *,
        actor: User,
        name: str | None = None,
        description: str | None = None,
        status: ProjectStatus | None = None,
    ) -> Project:
        changed: list[str] = []
        if name is not None and name != project.name:
            project.name = name
            changed.append("name")
        if description is not None and description != project.description:
            project.description = description
            changed.append("description")
        if status is not None and status is not project.status:
            project.status = status
            changed.append("status")

        if changed:
            await self._bus.publish_event(
                PROJECT_UPDATED,
                actor_id=actor.id,
                payload={
                    "project_id": str(project.id),
                    "organization_id": str(project.organization_id),
                    "changed": changed,
                    "summary": f"updated {', '.join(changed)} of project {project.name!r}",
                },
            )
        return project

    async def delete(self, project: Project, *, actor: User) -> None:
        project_id, organization_id = project.id, project.organization_id
        name = project.name
        await self._projects.delete(project)
        await self._bus.publish_event(
            PROJECT_DELETED,
            actor_id=actor.id,
            payload={
                "project_id": str(project_id),
                "organization_id": str(organization_id),
                "summary": f"deleted project {name!r}",
            },
        )

    async def require(self, project_id: UUID, *, organization_id: UUID) -> Project:
        project = await self._projects.get(project_id, organization_id=organization_id)
        if project is None:
            raise NotFoundError(f"Project {project_id} not found")
        return project
