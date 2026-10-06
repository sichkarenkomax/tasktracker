"""Organizations, membership and the isolation boundary."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import (
    auth_headers,
    create_organization,
    register_user,
    unique_email,
)


async def add_member(
    client: AsyncClient,
    token: str,
    organization_id: str,
    *,
    email: str | None = None,
    user_id: str | None = None,
    role: str = "member",
) -> Any:
    payload: dict[str, Any] = {"role": role}
    if email is not None:
        payload["email"] = email
    if user_id is not None:
        payload["user_id"] = user_id
    return await client.post(
        f"/api/v1/organizations/{organization_id}/members",
        json=payload,
        headers=auth_headers(token),
    )


class TestCreate:
    async def test_creator_becomes_owner(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Acme Corp"},
            headers=auth_headers(session["access_token"]),
        )

        assert response.status_code == 201
        body = response.json()
        assert body["slug"] == "acme-corp"

        members = await client.get(
            f"/api/v1/organizations/{body['id']}/members",
            headers=auth_headers(session["access_token"]),
        )
        assert [m["role"] for m in members.json()] == ["owner"]
        assert members.json()[0]["user_id"] == session["user"]["id"]

    async def test_slug_is_derived_when_absent(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "  Ökonomie GmbH & Co  "},
            headers=auth_headers(session["access_token"]),
        )

        assert response.status_code == 201
        assert response.json()["slug"] == "konomie-gmbh-co"

    async def test_explicit_slug_is_kept(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Acme", "slug": "acme"},
            headers=auth_headers(session["access_token"]),
        )

        assert response.json()["slug"] == "acme"

    async def test_slug_must_be_url_safe(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Acme", "slug": "Not A Slug"},
            headers=auth_headers(session["access_token"]),
        )

        assert response.status_code == 422

    async def test_slug_is_globally_unique(self, client: AsyncClient) -> None:
        first = await register_user(client)
        await create_organization(client, first["access_token"], slug="taken")
        second = await register_user(client)

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Other", "slug": "taken"},
            headers=auth_headers(second["access_token"]),
        )

        assert response.status_code == 409

    async def test_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.post("/api/v1/organizations", json={"name": "Acme"})

        assert response.status_code == 401


class TestRead:
    async def test_lists_only_my_organizations(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        mine = await client.get("/api/v1/organizations", headers=auth_headers(owner["token"]))
        theirs = await client.get("/api/v1/organizations", headers=auth_headers(outsider["token"]))

        assert [o["id"] for o in mine.json()] == [owner["organization"]["id"]]
        assert theirs.json() == []

    async def test_returns_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Acme"

    async def test_non_member_is_denied(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "permission_denied"


class TestUpdate:
    async def test_owner_can_rename(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}",
            json={"name": "Acme Incorporated", "description": "We make things"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Acme Incorporated"
        assert response.json()["description"] == "We make things"

    async def test_viewer_cannot_rename(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client,
            owner["token"],
            owner["organization"]["id"],
            email=outsider["user"]["email"],
            role="viewer",
        )

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}",
            json={"name": "Hijacked"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestDelete:
    async def test_owner_can_delete(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        organization_id = owner["organization"]["id"]

        deleted = await client.delete(
            f"/api/v1/organizations/{organization_id}",
            headers=auth_headers(owner["token"]),
        )
        gone = await client.get(
            f"/api/v1/organizations/{organization_id}",
            headers=auth_headers(owner["token"]),
        )

        assert deleted.status_code == 204
        assert gone.status_code == 403

    async def test_non_member_cannot_delete(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestMembership:
    async def test_add_by_email(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await add_member(
            client,
            owner["token"],
            owner["organization"]["id"],
            email=outsider["user"]["email"],
        )

        assert response.status_code == 201
        assert response.json()["user_id"] == outsider["user"]["id"]
        assert response.json()["role"] == "member"

    async def test_add_by_user_id(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await add_member(
            client,
            owner["token"],
            owner["organization"]["id"],
            user_id=outsider["user"]["id"],
        )

        assert response.status_code == 201

    async def test_unknown_user_is_reported_as_not_found(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await add_member(
            client, owner["token"], owner["organization"]["id"], email=unique_email()
        )

        assert response.status_code == 404

    async def test_duplicate_membership_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client, owner["token"], owner["organization"]["id"], email=outsider["user"]["email"]
        )

        response = await add_member(
            client, owner["token"], owner["organization"]["id"], email=outsider["user"]["email"]
        )

        assert response.status_code == 409

    async def test_exactly_one_identifier_is_required(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await add_member(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 422

    async def test_member_can_now_read_the_organization(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client, owner["token"], owner["organization"]["id"], email=outsider["user"]["email"]
        )

        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 200

    async def test_role_can_be_changed(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client, owner["token"], owner["organization"]["id"], email=outsider["user"]["email"]
        )

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{outsider['user']['id']}",
            json={"role": "admin"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["role"] == "admin"

    async def test_the_last_owner_cannot_be_demoted(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{owner['user']['id']}",
            json={"role": "admin"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_an_admin_cannot_edit_an_owner(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client,
            owner["token"],
            owner["organization"]["id"],
            email=outsider["user"]["email"],
            role="admin",
        )

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{owner['user']['id']}",
            json={"role": "viewer"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_an_admin_cannot_promote_themselves_to_owner(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client,
            owner["token"],
            owner["organization"]["id"],
            email=outsider["user"]["email"],
            role="admin",
        )

        response = await client.patch(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{outsider['user']['id']}",
            json={"role": "owner"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_member_can_be_removed(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await add_member(
            client, owner["token"], owner["organization"]["id"], email=outsider["user"]["email"]
        )

        removed = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{outsider['user']['id']}",
            headers=auth_headers(owner["token"]),
        )
        after = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}",
            headers=auth_headers(outsider["token"]),
        )

        assert removed.status_code == 204
        assert after.status_code == 403

    async def test_removing_a_non_member_is_reported(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        stranger = await register_user(client)

        response = await client.delete(
            f"/api/v1/organizations/{owner['organization']['id']}/members/{stranger['user']['id']}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404

    async def test_members_list_carries_the_user_summary(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            headers=auth_headers(owner["token"]),
        )

        member = response.json()[0]
        assert member["user"]["username"] == owner["user"]["username"]
        assert "password_hash" not in member["user"]
