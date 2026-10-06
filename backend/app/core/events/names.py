"""Core event names.

Declared centrally so that subscribers and the Activity projector refer to the
same strings. Modules follow the `entity.action` convention and declare their
own events in their manifest.
"""

from __future__ import annotations

from typing import Final

USER_REGISTERED: Final = "user.registered"
USER_LOGGED_IN: Final = "user.logged_in"
USER_PROFILE_UPDATED: Final = "user.profile_updated"
USER_PASSWORD_CHANGED: Final = "user.password_changed"

ORGANIZATION_CREATED: Final = "organization.created"
ORGANIZATION_UPDATED: Final = "organization.updated"
ORGANIZATION_DELETED: Final = "organization.deleted"
ORGANIZATION_MEMBER_ADDED: Final = "organization.member_added"
ORGANIZATION_MEMBER_ROLE_CHANGED: Final = "organization.member_role_changed"
ORGANIZATION_MEMBER_REMOVED: Final = "organization.member_removed"

TEAM_CREATED: Final = "team.created"
TEAM_UPDATED: Final = "team.updated"
TEAM_DELETED: Final = "team.deleted"
TEAM_MEMBER_ADDED: Final = "team.member_added"
TEAM_MEMBER_REMOVED: Final = "team.member_removed"

PROJECT_CREATED: Final = "project.created"
PROJECT_UPDATED: Final = "project.updated"
PROJECT_DELETED: Final = "project.deleted"
