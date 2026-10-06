"""The role -> permission matrix, enforced through real HTTP requests.

These tests are the executable form of docs/architecture.md section 25: a
permission check must always resolve inside an organization, and a role must
never grant more than the matrix says.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers


async def join(
    client: AsyncClient,
    owner: dict[str, Any],
    invitee: dict[str, Any],
    role: str,
) -> None:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": invitee["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text


async def get_organization(client: AsyncClient, token: str, organization_id: str) -> Any:
    return await client.get(f"/api/v1/organizations/{organization_id}", headers=auth_headers(token))


class TestMembershipGate:
    async def test_a_non_member_cannot_read(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await get_organization(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"

    async def test_an_anonymous_caller_is_rejected_before_any_lookup(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """401 rather than 403: no membership question is even asked."""
        # The client carries the session cookie from previous requests.
        client.cookies.clear()

        response = await get_organization(client, "", owner["organization"]["id"])

        assert response.status_code == 401

    async def test_a_cleared_session_is_really_anonymous(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The auth cookie alone authenticates - there is no server-side session."""
        client.cookies.clear()

        response = await get_organization(client, "", owner["organization"]["id"])

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "authentication_error"

    async def test_every_route_requires_the_organization_context(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A project read without organization_id cannot be authorized at all."""
        projects = await client.get("/api/v1/projects", headers=auth_headers(owner["token"]))

        assert projects.status_code == 422


class TestViewerIsReadOnly:
    async def test_can_read(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "viewer")

        response = await get_organization(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 200

    async def test_cannot_rename_the_organization(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "viewer")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403
        assert response.json()["error"]["details"]["required"] == "organization.update"

    async def test_cannot_manage_members(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "viewer")

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"user_id": owner["user"]["id"]},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_cannot_change_settings(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "viewer")

        response = await client.put(
            f"/api/v1/organizations/{owner['organization']['id']}/settings",
            json={"values": {"locale": "de"}},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestMember:
    async def test_can_manage_teams(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "member")

        response = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/teams",
            json={"name": "Backend"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 201

    async def test_cannot_delete_a_team(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await client.post(
            f"/api/v1/organizations/{organization_id}/teams",
            json={"name": "Backend"},
            headers=auth_headers(owner["token"]),
        )
        await join(client, owner, outsider, "member")

        response = await client.delete(
            f"/api/v1/organizations/{organization_id}/teams/{created.json()['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_cannot_change_the_organization(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "member")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestAdmin:
    async def test_can_rename_the_organization(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "admin")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}",
            json={"name": "Renamed"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 200

    async def test_can_delete_a_team(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await client.post(
            f"/api/v1/organizations/{organization_id}/teams",
            json={"name": "Backend"},
            headers=auth_headers(owner["token"]),
        )
        await join(client, owner, outsider, "admin")

        response = await client.delete(
            f"/api/v1/organizations/{organization_id}/teams/{created.json()['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 204

    async def test_cannot_edit_an_owner(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "admin")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{owner['user']['id']}",
            json={"role": "viewer"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403
        assert response.json()["error"]["details"]["target_role"] == "owner"

    async def test_cannot_edit_another_admin(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        from tests.conftest import register_user

        peer = await register_user(client, prefix="peer")
        await join(client, owner, outsider, "admin")
        await join(client, owner, {"user": peer["user"]}, "admin")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{peer['user']['id']}",
            json={"role": "viewer"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestOwner:
    async def test_can_delete_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 204

    async def test_can_promote_a_member_to_admin(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "member")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{outsider['user']['id']}",
            json={"role": "admin"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200

    async def test_can_hand_out_ownership(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await join(client, owner, outsider, "member")

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{outsider['user']['id']}",
            json={"role": "owner"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
