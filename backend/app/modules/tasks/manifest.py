"""Tasks module manifest.

The declared permissions and events are the module's public contract: other
modules and the future Automation Engine rely on them
(docs/architecture.md, sections 22, 25, 36).

Event names follow the platform's ``entity.action`` convention so that the
Activity projector, which only knows the convention, records them without Core
ever learning that Tasks exists (section 19).
"""

from app.core.modules.manifest import ModuleManifest
from app.modules.tasks import permissions

MANIFEST = ModuleManifest(
    id="tasks",
    name="Tasks",
    version="0.2.0",
    description="Task management - the first functional module of the platform.",
    dependencies=(),
    permissions=tuple(sorted(permissions.ALL)),
    routes=("/api/v1/tasks",),
    events=(
        "task.created",
        "task.updated",
        "task.status_changed",
        "task.priority_changed",
        "task.assigned",
        # Emitted in addition to task.status_changed: the transition into and out
        # of a terminal status is what subscribers care about (section 21).
        "task.completed",
        "task.reopened",
        "task.deleted",
        "comment.created",
        "comment.deleted",
        # Co-assignees and watchers. Emitted so the feed can say who joined a
        # task, which is otherwise invisible from the events above.
        "task.participant_added",
        "task.participant_removed",
    ),
)
