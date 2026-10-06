"""Activity projection.

A single wildcard subscriber turns every domain event into an activity row.
This is the mechanism that keeps Core ignorant of individual modules: Tasks,
CRM and Chat all produce events, and none of them know Activity exists
(docs/architecture.md, sections 19 and 21).

Events carrying a "skip_activity" flag are ignored, which lets noisy events
such as `user.logged_in` be excluded without special-casing handlers.
"""

from __future__ import annotations

import enum
import logging
from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.activity.models import Activity
from app.core.events.types import DomainEvent

logger = logging.getLogger(__name__)

#: Events that must not produce an activity row.
IGNORED_EVENTS = frozenset({"user.logged_in"})


class ActivityProjector:
    """Persists events. One instance per application, not per request."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self._session_factory = session_factory

    async def __call__(self, event: DomainEvent) -> None:
        if event.name in IGNORED_EVENTS or event.payload.get("skip_activity"):
            return

        activity = Activity(
            organization_id=_as_uuid(event.payload.get("organization_id")),
            actor_id=event.actor_id,
            action=event.name,
            entity_type=event.payload.get("entity_type") or _entity_from_name(event.name),
            entity_id=event.payload.get("entity_id") or _entity_id_from_payload(event.payload),
            summary=event.payload.get("summary"),
            payload=_json_safe(dict(event.payload)),
        )

        # Own transaction: events arrive only after the business transaction
        # committed, so a projection failure must not be able to undo that.
        # A failure is raised to the bus, which isolates it per handler.
        async with self._session_factory() as session:
            session.add(activity)
            await session.commit()


def _entity_from_name(event_name: str) -> str:
    """`task.created` -> `task`, `organization.member_added` -> `organization`.

    Event names are ``entity.action`` by convention, so the prefix already names
    the entity the activity is about.
    """
    return event_name.split(".", 1)[0]


def _entity_id_from_payload(payload: Mapping[str, Any]) -> str | None:
    for key in ("task_id", "project_id", "team_id", "organization_id", "user_id"):
        value = payload.get(key)
        if value is not None:
            return str(value)
    return None


def _as_uuid(value: Any) -> UUID | None:
    if value is None:
        return None
    return value if isinstance(value, UUID) else UUID(str(value))


def _json_safe(payload: dict[str, Any]) -> dict[str, Any]:
    """Coerce values into something JSONB can store."""
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, UUID):
            safe[key] = str(value)
        elif isinstance(value, enum.Enum):
            safe[key] = str(value.value)
        else:
            safe[key] = value
    return safe
