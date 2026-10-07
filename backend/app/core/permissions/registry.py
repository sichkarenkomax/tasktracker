"""Permission catalogue owned by Core.

Modules declare their own permission strings in their manifest
(docs/architecture.md, section 25). The effective catalogue is the union of
the two, so a check never has to know where a permission came from.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Final

if TYPE_CHECKING:  # pragma: no cover
    from app.core.modules import ModuleManager

#: Wildcard accepted by any role check; granted only to organization owners.
ALL: Final = "*"

#: Permissions that Core itself protects.
CORE_PERMISSIONS: Final[frozenset[str]] = frozenset(
    {
        # Users
        "user.view",
        "user.update",
        # Organizations
        "organization.view",
        "organization.create",
        "organization.update",
        "organization.delete",
        "organization.members.manage",
        "organization.settings.manage",
        # Teams
        "team.view",
        "team.create",
        "team.update",
        "team.delete",
        "team.members.manage",
        # Organization structure: departments, positions, reporting lines.
        # Split in two on purpose - almost everybody needs to see who reports to
        # whom, and almost nobody should be able to redraw the chart.
        "orgstructure.view",
        "orgstructure.manage",
        # Projects
        "project.view",
        "project.create",
        "project.update",
        "project.delete",
        # Activity
        "activity.view",
    }
)


def catalogue(module_permissions: frozenset[str] | set[str] | None = None) -> set[str]:
    """Full permission catalogue: Core plus whatever modules declare."""
    return set(CORE_PERMISSIONS) | set(module_permissions or ())


def describe(manager: ModuleManager) -> dict[str, Any]:
    """Split the catalogue into core and per-module buckets for introspection."""
    module_permissions: dict[str, list[str]] = {}
    for module in manager.modules.values():
        module_permissions[module.manifest.id] = list(module.manifest.permissions)
    return {
        "core": sorted(CORE_PERMISSIONS),
        "modules": {key: sorted(value) for key, value in sorted(module_permissions.items())},
    }
