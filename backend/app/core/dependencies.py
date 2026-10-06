"""Shared FastAPI dependencies that do not belong to a single Core package."""

from __future__ import annotations

from typing import Annotated, cast

from fastapi import Depends, Request

from app.core.events.bus import EventBus


def get_event_bus(request: Request) -> EventBus:
    """The single in-process bus owned by the Module Manager."""
    return cast(EventBus, request.app.state.modules.bus)


EventBusDep = Annotated[EventBus, Depends(get_event_bus)]
