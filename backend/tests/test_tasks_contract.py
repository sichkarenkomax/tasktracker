"""The Tasks module's contract with the platform.

Three things have to agree, and no type system enforces them:

* the permission strings the module checks;
* the strings its manifest advertises to ``GET /api/v1/system``;
* the strings Core's role matrix grants.

A permission that exists in only one of the three fails silently: a role either
holds a right nobody checks, or the module demands a right nobody holds and every
route answers 403 for a reason no log explains. The same is true of event names -
the Activity projector recognises a shape, not a list.
"""

from __future__ import annotations

import pytest

from app.core.events.types import EVENT_NAME_PATTERN
from app.core.permissions.roles import (
    ADMIN_PERMISSIONS,
    ALL,
    MEMBER_PERMISSIONS,
    OWNER_PERMISSIONS,
    ROLE_PERMISSIONS,
    VIEWER_PERMISSIONS,
    OrganizationRole,
    grants,
)
from app.modules.tasks import permissions as task_permissions
from app.modules.tasks import service
from app.modules.tasks.manifest import MANIFEST

#: A permission no module has declared yet, standing in for the next one.
FUTURE_PERMISSION = "kanban.column.moved"


def _published_event_names() -> set[str]:
    """Every event name the service publishes, read from its module-level Finals."""
    names = set()
    for key, value in vars(service).items():
        if key.isupper() and isinstance(value, str) and EVENT_NAME_PATTERN.match(value):
            names.add(value)
    return names


class TestPermissionContract:
    def test_manifest_advertises_exactly_what_the_module_checks(self) -> None:
        assert frozenset(MANIFEST.permissions) == task_permissions.ALL

    def test_every_permission_is_a_non_empty_dotted_string(self) -> None:
        for permission in task_permissions.ALL:
            assert "." in permission
            assert permission == permission.strip().lower()

    def test_no_task_permission_is_also_a_core_permission(self) -> None:
        """A collision would mean Core and the module grant it independently."""
        from app.core.permissions.registry import CORE_PERMISSIONS

        assert not task_permissions.ALL & CORE_PERMISSIONS

    def test_no_role_spellings_collide(self) -> None:
        for role, held in ROLE_PERMISSIONS.items():
            assert len(held) == len({p for p in held}), role


class TestEventContract:
    def test_the_service_publishes_exactly_what_the_manifest_declares(self) -> None:
        assert _published_event_names() == set(MANIFEST.events)

    def test_names_follow_the_platform_convention(self) -> None:
        """The projector recognises ``entity.action`` and nothing else."""
        for name in MANIFEST.events:
            assert EVENT_NAME_PATTERN.match(name), name
            assert name.split(".")[0] in {"task", "comment"}

    def test_the_module_subscribes_to_nothing_of_its_own(self) -> None:
        """Activity lives in Core; a module must not need to know it exists."""
        from app.modules.tasks.events import EVENT_HANDLERS

        assert EVENT_HANDLERS == ()


class TestRoleMatrix:
    def test_owner_holds_every_task_permission(self) -> None:
        for permission in task_permissions.ALL:
            assert grants(OrganizationRole.OWNER, permission), permission

    def test_member_can_do_the_work_but_not_remove_it(self) -> None:
        for permission in (
            task_permissions.VIEW,
            task_permissions.CREATE,
            task_permissions.UPDATE,
            task_permissions.ASSIGN,
            task_permissions.COMPLETE,
            task_permissions.COMMENT_CREATE,
            task_permissions.COMMENT_DELETE,
        ):
            assert permission in MEMBER_PERMISSIONS, permission
        assert task_permissions.DELETE not in MEMBER_PERMISSIONS

    def test_admin_can_remove_a_task(self) -> None:
        assert task_permissions.DELETE in ADMIN_PERMISSIONS

    def test_viewer_is_read_only(self) -> None:
        assert task_permissions.VIEW in VIEWER_PERMISSIONS
        assert {task_permissions.VIEW} == (VIEWER_PERMISSIONS & task_permissions.ALL)

    def test_owners_cover_permissions_of_future_modules(self) -> None:
        """A permission the next module invents must already work for owners."""
        assert grants(OrganizationRole.OWNER, FUTURE_PERMISSION)
        assert ALL in OWNER_PERMISSIONS

    @pytest.mark.parametrize("role", ["viewer", "member", "admin"])
    def test_the_wildcard_does_not_leak_into_lesser_roles(self, role: str) -> None:
        """``grants`` must not read ``*`` as a full pass for every role."""
        assert ALL not in ROLE_PERMISSIONS[OrganizationRole(role)]
        assert not grants(OrganizationRole(role), FUTURE_PERMISSION)

    def test_roles_are_strictly_nested(self) -> None:
        """A viewer must not be able to do what a member cannot."""
        assert VIEWER_PERMISSIONS < MEMBER_PERMISSIONS < ADMIN_PERMISSIONS
