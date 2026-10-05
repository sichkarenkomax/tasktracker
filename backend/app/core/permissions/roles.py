"""Organization roles and what they grant.

Phase 1 keeps this deliberately small: a fixed set of roles per organization.
Project-scoped and custom roles arrive later (docs/architecture.md, section 25)
without changing the permission strings themselves.
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
    return permission in ROLE_PERMISSIONS[role]


def outranks(actor: OrganizationRole, target: OrganizationRole) -> bool:
    """True when `actor` may modify a member holding `target`."""
    return ROLE_RANK[actor] > ROLE_RANK[target]
