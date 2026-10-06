"""Role ranks and the permission matrix.

Pure unit tests: no database, no HTTP. The matrix is security-relevant data, so
it is worth pinning exactly what each role may do
(docs/architecture.md, section 25).
"""

from __future__ import annotations

import pytest

from app.core.permissions.registry import ALL, CORE_PERMISSIONS
from app.core.permissions.roles import (
    ADMIN_PERMISSIONS,
    MEMBER_PERMISSIONS,
    OWNER_PERMISSIONS,
    ROLE_MANAGEMENT_PERMISSIONS,
    ROLE_PERMISSIONS,
    ROLE_RANK,
    VIEWER_PERMISSIONS,
    OrganizationRole,
    grants,
    outranks,
)


def declared_module_permissions() -> frozenset[str]:
    """Every permission advertised by a first-party module manifest.

    Read through discovery rather than imported from Tasks, so the check keeps
    working when the next module ships and nobody remembers to extend it.
    """
    from app.core.modules.registry import discover_modules

    return frozenset(
        permission for bundle in discover_modules() for permission in bundle.manifest.permissions
    )


class TestRanks:
    def test_ranks_are_strictly_ordered(self) -> None:
        assert (
            ROLE_RANK[OrganizationRole.OWNER]
            > ROLE_RANK[OrganizationRole.ADMIN]
            > ROLE_RANK[OrganizationRole.MEMBER]
            > ROLE_RANK[OrganizationRole.VIEWER]
        )

    @pytest.mark.parametrize(
        ("actor", "target"),
        [
            (OrganizationRole.OWNER, OrganizationRole.ADMIN),
            (OrganizationRole.OWNER, OrganizationRole.MEMBER),
            (OrganizationRole.OWNER, OrganizationRole.VIEWER),
            (OrganizationRole.ADMIN, OrganizationRole.MEMBER),
            (OrganizationRole.ADMIN, OrganizationRole.VIEWER),
            (OrganizationRole.MEMBER, OrganizationRole.VIEWER),
        ],
    )
    def test_higher_outranks_lower(self, actor: OrganizationRole, target: OrganizationRole) -> None:
        assert outranks(actor, target)

    @pytest.mark.parametrize(
        ("actor", "target"),
        [
            (OrganizationRole.OWNER, OrganizationRole.OWNER),
            (OrganizationRole.ADMIN, OrganizationRole.ADMIN),
            (OrganizationRole.ADMIN, OrganizationRole.OWNER),
            (OrganizationRole.MEMBER, OrganizationRole.MEMBER),
            (OrganizationRole.MEMBER, OrganizationRole.ADMIN),
            (OrganizationRole.VIEWER, OrganizationRole.MEMBER),
        ],
    )
    def test_equal_or_lower_does_not_outrank(
        self, actor: OrganizationRole, target: OrganizationRole
    ) -> None:
        assert not outranks(actor, target)


class TestMatrix:
    def test_every_role_is_registered(self) -> None:
        assert set(ROLE_PERMISSIONS) == set(OrganizationRole)
        assert set(ROLE_MANAGEMENT_PERMISSIONS) == set(OrganizationRole)

    def test_nothing_grants_an_unknown_permission(self) -> None:
        """A permission nobody declared is a typo or a privilege nobody asked for,
        and it is invisible at runtime because no route ever checks it."""
        declared = set(CORE_PERMISSIONS) | {ALL} | declared_module_permissions()
        for role, permissions in ROLE_PERMISSIONS.items():
            unknown = permissions - declared
            assert not unknown, f"{role} grants permissions outside the catalogue: {unknown}"

    def test_owner_holds_the_wildcard(self) -> None:
        assert grants(OrganizationRole.OWNER, ALL)
        assert grants(OrganizationRole.OWNER, "some.future_module.permission")
        assert not grants(OrganizationRole.ADMIN, "some.future_module.permission")

    def test_permission_sets_nest_by_privilege(self) -> None:
        assert VIEWER_PERMISSIONS < MEMBER_PERMISSIONS
        assert MEMBER_PERMISSIONS < ADMIN_PERMISSIONS

    def test_owners_outrank_admins_without_listing_every_right(self) -> None:
        """The owner's set is deliberately *not* a superset of the admin's: it is
        the wildcard.

        Spelling every permission out for the owner would mean editing this file
        each time a module ships, and forgetting to would lock the owner out of
        their own platform.
        """
        assert ALL in OWNER_PERMISSIONS
        for permission in ADMIN_PERMISSIONS:
            assert grants(OrganizationRole.OWNER, permission), permission
        assert not ADMIN_PERMISSIONS < OWNER_PERMISSIONS

    def test_viewer_can_only_read(self) -> None:
        """A viewer's whole power set consists of `*.view` permissions."""
        assert VIEWER_PERMISSIONS
        assert all(permission.endswith(".view") for permission in VIEWER_PERMISSIONS)
        assert "project.create" not in VIEWER_PERMISSIONS
        assert "project.delete" not in VIEWER_PERMISSIONS
        assert "organization.update" not in VIEWER_PERMISSIONS

    def test_member_can_work_but_not_administrate(self) -> None:
        assert grants(OrganizationRole.MEMBER, "project.create")
        assert grants(OrganizationRole.MEMBER, "project.update")
        assert grants(OrganizationRole.MEMBER, "team.create")
        assert not grants(OrganizationRole.MEMBER, "project.delete")
        assert not grants(OrganizationRole.MEMBER, "organization.delete")
        assert not grants(OrganizationRole.MEMBER, "organization.members.manage")

    def test_admin_can_administer_but_not_own(self) -> None:
        assert grants(OrganizationRole.ADMIN, "organization.members.manage")
        assert grants(OrganizationRole.ADMIN, "organization.settings.manage")
        assert grants(OrganizationRole.ADMIN, "project.delete")
        assert not outranks(OrganizationRole.ADMIN, OrganizationRole.OWNER)

    @pytest.mark.parametrize(
        "role",
        [OrganizationRole.ADMIN, OrganizationRole.MEMBER, OrganizationRole.VIEWER],
    )
    def test_no_role_but_owner_can_hand_out_ownership(self, role: OrganizationRole) -> None:
        assert not grants(role, ALL)

    def test_viewer_has_no_management_power(self) -> None:
        assert ROLE_MANAGEMENT_PERMISSIONS[OrganizationRole.VIEWER] == frozenset()
        assert ROLE_MANAGEMENT_PERMISSIONS[OrganizationRole.MEMBER] == frozenset()


class TestRolesAreComparable:
    def test_role_is_a_string_enum(self) -> None:
        assert OrganizationRole.OWNER == "owner"
        assert str(OrganizationRole.VIEWER) == "viewer"
        assert OrganizationRole("admin") is OrganizationRole.ADMIN

    def test_roles_sort_from_most_to_least_privileged(self) -> None:
        ordered = sorted(OrganizationRole, key=lambda role: -ROLE_RANK[role])

        assert ordered == [
            OrganizationRole.OWNER,
            OrganizationRole.ADMIN,
            OrganizationRole.MEMBER,
            OrganizationRole.VIEWER,
        ]
