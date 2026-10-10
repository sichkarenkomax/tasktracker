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
USER_EMAIL_CHANGED: Final = "user.email_changed"
USER_STATUS_CHANGED: Final = "user.status_changed"
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

# Organization structure. `org.` rather than `organization.` so a subscriber can
# filter the chart separately from the tenant record itself.
ORG_DEPARTMENT_CREATED: Final = "org.department_created"
ORG_DEPARTMENT_UPDATED: Final = "org.department_updated"
ORG_DEPARTMENT_DELETED: Final = "org.department_deleted"
ORG_POSITION_CREATED: Final = "org.position_created"
ORG_POSITION_UPDATED: Final = "org.position_updated"
ORG_POSITION_DELETED: Final = "org.position_deleted"
ORG_MEMBER_PLACED: Final = "org.member_placed"
ORG_DEPUTY_ADDED: Final = "org.deputy_added"
ORG_DEPUTY_REMOVED: Final = "org.deputy_removed"

PROJECT_CREATED: Final = "project.created"
PROJECT_UPDATED: Final = "project.updated"
PROJECT_DELETED: Final = "project.deleted"
