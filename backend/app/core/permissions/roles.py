"""Organization roles and what they grant.

Phase 1 keeps this deliberately small: a fixed set of roles per organization.
Project-scoped and custom roles arrive later (docs/architecture.md, section 25)
without changing the permission strings themselves.

Task and comment permissions are spelled out literally rather than imported from
the Tasks module. Core must not depend on a module it is allowed to disable; a
test compares this catalogue with the module's manifest, which catches a typo or
a permission nobody granted without creating an import edge from Core to Tasks.
"""

from __future__ import annotations

from enum import StrEnum

from app.core.permissions.registry import ALL, CORE_PERMISSIONS

# Ordered from most to least privileged - used for comparisons and sorting.
MEMBER_PERMISSIONS: frozenset[str] = frozenset(
    {
        "user.view",
        "organization.view",
        "team.view",
        "team.create",
        "team.update",
        "team.members.manage",
        "project.view",
        "project.create",
        "project.update",
        "activity.view",
        # Tasks module: members do the work, only admins remove it.
        "task.view",
        "task.create",
        "task.update",
        "task.assign",
        "task.complete",
        "comment.create",
        "comment.delete",
    }
)

ADMIN_PERMISSIONS: frozenset[str] = MEMBER_PERMISSIONS | frozenset(
    {
        "organization.update",
        "organization.delete",
        "organization.members.manage",
        "organization.settings.manage",
        "team.delete",
        "project.delete",
        "task.delete",
    }
)

#: The owner implicitly holds every permission, including future ones.
OWNER_PERMISSIONS: frozenset[str] = frozenset(CORE_PERMISSIONS) | {ALL}

VIEWER_PERMISSIONS: frozenset[str] = frozenset(
    {
        "user.view",
        "organization.view",
        "team.view",
        "project.view",
        "activity.view",
        # Read-only: a viewer may look at tasks and touch nothing else.
        "task.view",
    }
)


class OrganizationRole(StrEnum):
    OWNER = "owner"
    ADMIN = "admin"
    MEMBER = "member"
    VIEWER = "viewer"


ROLE_PERMISSIONS: dict[OrganizationRole, frozenset[str]] = {
    OrganizationRole.OWNER: OWNER_PERMISSIONS,
    OrganizationRole.ADMIN: ADMIN_PERMISSIONS,
    OrganizationRole.MEMBER: MEMBER_PERMISSIONS,
    OrganizationRole.VIEWER: VIEWER_PERMISSIONS,
}

#: Privileges a role must not be able to hand out or take away.
ROLE_MANAGEMENT_PERMISSIONS: dict[OrganizationRole, frozenset[str]] = {
    OrganizationRole.OWNER: frozenset({ALL}),
    OrganizationRole.ADMIN: frozenset(
        {"organization.update", "organization.members.manage", "organization.settings.manage"}
    ),
    OrganizationRole.MEMBER: frozenset(),
    OrganizationRole.VIEWER: frozenset(),
}

ROLE_RANK: dict[OrganizationRole, int] = {
    OrganizationRole.OWNER: 3,
    OrganizationRole.ADMIN: 2,
    OrganizationRole.MEMBER: 1,
    OrganizationRole.VIEWER: 0,
}


def grants(role: OrganizationRole, permission: str) -> bool:
    """True when `role` may perform `permission`.

    A role holding the wildcard (``*``) is granted everything, including
    permissions that modules register later - otherwise the owner would be
    locked out of a feature the day its module ships.
    """
    permissions = ROLE_PERMISSIONS[role]
    return ALL in permissions or permission in permissions


def outranks(actor: OrganizationRole, target: OrganizationRole) -> bool:
    """True when `actor` may modify a member holding `target`."""
    return ROLE_RANK[actor] > ROLE_RANK[target]
