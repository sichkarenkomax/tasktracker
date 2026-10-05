"""Tasks module manifest.

The declared permissions and events are the module's public contract: other
modules and the future Automation Engine rely on them
(docs/architecture.md, sections 22, 25, 36).
"""

from app.core.modules.manifest import ModuleManifest

MANIFEST = ModuleManifest(
    id="tasks",
    name="Tasks",
    version="0.1.0",
    description="Task management - the first functional module of the platform.",
    dependencies=(),
    permissions=(
        "task.view",
        "task.create",
        "task.update",
        "task.delete",
        "task.assign",
        "task.complete",
    ),
    routes=("/api/v1/tasks",),
    events=(
        "task.created",
        "task.updated",
        "task.completed",
        "task.assigned",
        "comment.created",
    ),
)
