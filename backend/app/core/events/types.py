"""Event value object."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Any
from uuid import UUID

#: Dotted lowercase names, e.g. "task.created" or "crm.deal.stage_changed".
EVENT_NAME_PATTERN = re.compile(r"^[a-z][a-z0-9]*(?:\.[a-z0-9_]+)+$")


class InvalidEventName(ValueError):
    """Raised when an event name does not follow the naming convention."""


def utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class DomainEvent:
    """An immutable, in-process domain event.

    Events carry data, never ORM entities: a module must not leak its internal
    models through the bus (docs/architecture.md, section 5).
    """

    name: str
    payload: Mapping[str, Any] = field(default_factory=dict)
    actor_id: UUID | None = None
    correlation_id: str | None = None
    occurred_at: datetime = field(default_factory=utcnow)

    def __post_init__(self) -> None:
        if not EVENT_NAME_PATTERN.match(self.name):
            raise InvalidEventName(
                f"Event name must match {EVENT_NAME_PATTERN.pattern!r}, got {self.name!r}"
            )
        object.__setattr__(self, "payload", MappingProxyType(dict(self.payload)))

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "payload": dict(self.payload),
            "actor_id": str(self.actor_id) if self.actor_id else None,
            "correlation_id": self.correlation_id,
            "occurred_at": self.occurred_at.isoformat(),
        }
