"""Activity repository and API."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Query
from pydantic import BaseModel, ConfigDict
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.activity.models import Activity
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.permissions.service import AuthorizationService
from app.core.users.models import User

router = APIRouter(prefix="/activity", tags=["activity"])


class ActivityRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    organization_id: UUID | None
    actor_id: UUID | None
    action: str
    entity_type: str | None
    entity_id: str | None
    summary: str | None
    payload: dict[str, Any]


class ActivityPage(BaseModel):
    items: list[ActivityRead]
    total: int
    limit: int
    offset: int


async def list_activity(
    session: AsyncSession,
    *,
    organization_id: UUID,
    user: User,
    limit: int,
    offset: int,
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: UUID | None = None,
    since: datetime | None = None,
) -> ActivityPage:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="activity.view"
    )

    filters: list[Any] = [Activity.organization_id == organization_id]
    if action:
        filters.append(Activity.action == action)
    if entity_type:
        filters.append(Activity.entity_type == entity_type)
    if entity_id:
        filters.append(Activity.entity_id == entity_id)
    if actor_id:
        filters.append(Activity.actor_id == actor_id)
    if since:
        filters.append(Activity.created_at >= since)

    total = int(
        await session.scalar(select(func.count()).select_from(Activity).where(*filters)) or 0
    )
    stmt = (
        select(Activity)
        .where(*filters)
        .order_by(Activity.created_at.desc(), Activity.id)
        .limit(limit)
        .offset(offset)
    )
    rows = (await session.scalars(stmt)).all()

    return ActivityPage(
        items=[ActivityRead.model_validate(row) for row in rows],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("", response_model=ActivityPage, summary="Activity feed for an organization")
async def read_activity(
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    action: str | None = None,
    entity_type: str | None = None,
    entity_id: str | None = None,
    actor_id: UUID | None = None,
    since: datetime | None = None,
) -> ActivityPage:
    return await list_activity(
        session,
        organization_id=organization_id,
        user=user,
        limit=limit,
        offset=offset,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        actor_id=actor_id,
        since=since,
    )


@router.get(
    "/entity/{entity_type}/{entity_id}",
    response_model=ActivityPage,
    summary="Activity for a single entity (e.g. a task)",
)
async def read_entity_activity(
    entity_type: str,
    entity_id: str,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
) -> ActivityPage:
    return await list_activity(
        session,
        organization_id=organization_id,
        user=user,
        limit=limit,
        offset=offset,
        entity_type=entity_type,
        entity_id=entity_id,
    )
