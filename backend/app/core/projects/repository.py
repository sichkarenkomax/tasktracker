"""Repository for projects."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.projects.models import Project, ProjectStatus
from app.database.helpers import count, fetch_all, fetch_one


class ProjectRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, project_id: UUID, *, organization_id: UUID) -> Project | None:
        return await fetch_one(
            self._session,
            select(Project).where(
                Project.id == project_id,
                Project.organization_id == organization_id,
            ),
        )

    async def list_for_organization(
        self,
        organization_id: UUID,
        *,
        status: ProjectStatus | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[Project]:
        statement = select(Project).where(Project.organization_id == organization_id)
        if status is not None:
            statement = statement.where(Project.status == status)
        statement = statement.order_by(Project.created_at.desc()).limit(limit).offset(offset)
        return await fetch_all(self._session, statement)

    async def name_taken(self, organization_id: UUID, name: str) -> bool:
        statement = (
            select(func.count())
            .select_from(Project)
            .where(
                Project.organization_id == organization_id,
                func.lower(Project.name) == name.lower(),
            )
        )
        return await count(self._session, statement) > 0

    async def add(self, project: Project) -> Project:
        self._session.add(project)
        await self._session.flush()
        return project

    async def delete(self, project: Project) -> None:
        await self._session.delete(project)
        await self._session.flush()
