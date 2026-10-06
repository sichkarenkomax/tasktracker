"""Projects: the work area every task module attaches to.

The interesting property here is not the CRUD but the tenant isolation: a
project id from one organization must be invisible in another, even when the
caller is a member of both.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def register_owner(client: AsyncClient) -> dict[str, Any]:
    session = await register_user(client, prefix="owner")
    token = session["access_token"]
    return {
        "token": token,
        "user": session["user"],
        "organization": await create_organization(client, token),
    }


async def add_member(
    client: AsyncClient, owner: dict[str, Any], invitee: dict[str, Any], role: str = "member"
) -> None:
    await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": invitee["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )


async def create_project(
    client: AsyncClient, token: str, organization_id: str, name: str = "Apollo"
) -> Any:
    return await client.post(
        "/api/v1/projects",
        json={"organization_id": organization_id, "name": name},
        headers=auth_headers(token),
    )


class TestCreate:
    async def test_defaults_to_planned(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        response = await create_project(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 201
        body = response.json()
        assert body["status"] == "planned"
        assert body["owner_id"] == owner["user"]["id"]
        assert body["organization_id"] == owner["organization"]["id"]

    async def test_outsider_cannot_create(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await create_project(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 403

    async def test_duplicate_name_in_one_organization_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await create_project(client, owner["token"], organization_id)

        response = await create_project(client, owner["token"], organization_id, "apollo")

        assert response.status_code == 409

    async def test_the_same_name_in_two_organizations_is_fine(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        other = await register_owner(client)
        await create_project(client, owner["token"], owner["organization"]["id"])

        response = await create_project(client, other["token"], other["organization"]["id"])

        assert response.status_code == 201


class TestRead:
    async def test_lists_projects_of_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await create_project(client, owner["token"], organization_id, "Apollo")
        await create_project(client, owner["token"], organization_id, "Gemini")

        response = await client.get(
            "/api/v1/projects",
            params={"organization_id": organization_id},
            headers=auth_headers(owner["token"]),
        )

        assert {p["name"] for p in response.json()} == {"Apollo", "Gemini"}

    async def test_organization_id_is_mandatory(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.get("/api/v1/projects", headers=auth_headers(owner["token"]))

        assert response.status_code == 422

    async def test_get_by_id(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        created = await create_project(client, owner["token"], owner["organization"]["id"])

        response = await client.get(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200

    async def test_a_member_of_both_organizations_still_sees_only_its_own(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Both tenants are legitimate for this caller, so the id must decide."""
        other = await register_owner(client)
        await add_member(client, other, owner)
        mine = await create_project(client, owner["token"], owner["organization"]["id"], "Mine")
        theirs = await create_project(client, other["token"], other["organization"]["id"], "Theirs")

        listing = await client.get(
            "/api/v1/projects",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        lookup = await client.get(
            f"/api/v1/projects/{theirs.json()['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert [p["name"] for p in listing.json()] == ["Mine"]
        assert lookup.status_code == 404
        assert mine.status_code == 201


class TestUpdate:
    async def test_rename_and_change_status(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_project(client, owner["token"], organization_id)

        response = await client.patch(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": organization_id},
            json={"name": "Apollo II", "status": "active"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Apollo II"
        assert response.json()["status"] == "active"

    async def test_viewer_cannot_update(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_project(client, owner["token"], organization_id)
        await add_member(client, owner, outsider, role="viewer")

        response = await client.patch(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": organization_id},
            json={"name": "Hijacked"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_member_can_update(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_project(client, owner["token"], organization_id)
        await add_member(client, owner, outsider, role="member")

        response = await client.patch(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": organization_id},
            json={"name": "Renamed by member"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 200


class TestDelete:
    async def test_admin_can_delete(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_project(client, owner["token"], organization_id)
        await add_member(client, owner, outsider, role="admin")

        deleted = await client.delete(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": organization_id},
            headers=auth_headers(outsider["token"]),
        )
        listed = await client.get(
            "/api/v1/projects",
            params={"organization_id": organization_id},
            headers=auth_headers(owner["token"]),
        )

        assert deleted.status_code == 204
        assert listed.json() == []

    async def test_plain_member_cannot_delete(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_project(client, owner["token"], organization_id)
        await add_member(client, owner, outsider, role="member")

        response = await client.delete(
            f"/api/v1/projects/{created.json()['id']}",
            params={"organization_id": organization_id},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403
