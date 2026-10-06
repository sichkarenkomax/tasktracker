"""Events the Tasks module handles.

Nothing is subscribed here on purpose: Activity in Core already subscribes to
every event with a wildcard, so a task shows up in the feed without the module
knowing Activity exists (docs/architecture.md, sections 19 and 21).

The entry exists as the documented extension point. The Automation Engine in a
later phase is exactly the kind of consumer that belongs here - and a workflow
like "assign a task and notify the assignee" then becomes a few lines in this
file instead of a change to Tasks or to Core.
"""

from __future__ import annotations

from typing import Final

#: Event name -> attribute on ``app.modules.tasks.service`` that declared it.
#: Kept next to the names themselves so a rename cannot leave one behind.
TASK_EVENT_NAMES: Final[tuple[str, ...]] = (
    "task.created",
    "task.updated",
    "task.status_changed",
    "task.priority_changed",
    "task.assigned",
    "task.completed",
    "task.reopened",
    "task.deleted",
    "comment.created",
    "comment.deleted",
)

#: ``discover_modules`` reads this attribute; an empty tuple is valid and means
#: "this module has no handlers of its own".
EVENT_HANDLERS: Final[tuple[tuple[str, object], ...]] = ()

__all__ = ["EVENT_HANDLERS", "TASK_EVENT_NAMES"]
