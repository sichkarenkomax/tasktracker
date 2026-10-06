"""Activity model.

Activity is a universal, read-optimised projection of domain events. It is
populated exclusively by a wildcard Event Bus subscriber, which is why Core
never needs to know that an event originated in Tasks (section 19) - the same
mechanism serves CRM, Chat and any future module.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, UUIDPrimaryKeyMixin


class Activity(UUIDPrimaryKeyMixin, Base):
    __tablename__ = "activities"

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )

    #: NULL for platform-level events that belong to no organization.
    organization_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
    )
    #: NULL for events performed by the system itself.
    actor_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
    )

    #: Event name, e.g. "task.created" or "organization.member_added".
    action: Mapped[str] = mapped_column(String(120), nullable=False)

    #: Free-form entity reference, e.g. ("task", "9f1c...").
    entity_type: Mapped[str | None] = mapped_column(String(60))
    entity_id: Mapped[str | None] = mapped_column(String(64))

    summary: Mapped[str | None] = mapped_column(Text)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        Index("ix_activities_organization_id_created_at", "organization_id", "created_at"),
        Index("ix_activities_actor_id", "actor_id"),
        Index("ix_activities_action", "action"),
    )

    def __repr__(self) -> str:
        return f"<Activity {self.action}>"
