"""Teams: CRUD plus membership, always inside one organization."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers


def teams_url(organization_id: str) -> str:
    return f"/api/v1/organizations/{organization_id}/teams"


async def create_team(client: AsyncClient, token: str, organization_id: str, name: str):
    return await client.post(
        teams_url(organization_id), json={"name": name}, headers=auth_headers(token)
    )


class TestCreate:
    async def test_owner_can_create(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        response = await create_team(client, owner["token"], owner["organization"]["id"], "Backend")

        assert response.status_code == 201
        body = response.json()
        assert body["name"] == "Backend"
        assert body["member_ids"] == []

    async def test_outsider_cannot_create(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await create_team(
            client, outsider["token"], owner["organization"]["id"], "Backend"
        )

        assert response.status_code == 403

    async def test_duplicate_name_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await create_team(client, owner["token"], organization_id, "Backend")

        response = await create_team(client, owner["token"], organization_id, "backend")

        assert response.status_code == 409


class TestRead:
    async def test_lists_teams_of_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await create_team(client, owner["token"], organization_id, "Alpha")
        await create_team(client, owner["token"], organization_id, "Beta")

        response = await client.get(
            teams_url(organization_id), headers=auth_headers(owner["token"])
        )

        assert [team["name"] for team in response.json()] == ["Alpha", "Beta"]

    async def test_teams_do_not_leak_across_organizations(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        other = await register_owner(client)
        mine = owner["organization"]["id"]
        theirs = other["organization"]["id"]
        await create_team(client, owner["token"], mine, "Mine")
        await create_team(client, other["token"], theirs, "Theirs")

        response = await client.get(teams_url(theirs), headers=auth_headers(other["token"]))

        assert [team["name"] for team in response.json()] == ["Theirs"]

    async def test_team_from_another_organization_is_not_found(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        created = await create_team(client, owner["token"], owner["organization"]["id"], "Backend")
        other = await register_owner(client)

        response = await client.get(
            f"{teams_url(other['organization']['id'])}/{created.json()['id']}",
            headers=auth_headers(other["token"]),
        )

        assert response.status_code == 404


class TestUpdateDelete:
    async def test_rename(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_team(client, owner["token"], organization_id, "Backend")

        response = await client.patch(
            f"{teams_url(organization_id)}/{created.json()['id']}",
            json={"name": "Platform"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["name"] == "Platform"

    async def test_delete(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_team(client, owner["token"], organization_id, "Backend")

        deleted = await client.delete(
            f"{teams_url(organization_id)}/{created.json()['id']}",
            headers=auth_headers(owner["token"]),
        )
        listed = await client.get(teams_url(organization_id), headers=auth_headers(owner["token"]))

        assert deleted.status_code == 204
        assert listed.json() == []


class TestTeamMembers:
    async def test_add_and_list_members(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_team(client, owner["token"], organization_id, "Backend")
        team_id = created.json()["id"]
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": outsider["user"]["email"]},
            headers=auth_headers(owner["token"]),
        )

        added = await client.post(
            f"{teams_url(organization_id)}/{team_id}/members",
            json={"user_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        read = await client.get(
            f"{teams_url(organization_id)}/{team_id}", headers=auth_headers(owner["token"])
        )

        assert added.status_code == 201
        assert read.json()["member_ids"] == [outsider["user"]["id"]]

    async def test_duplicate_member_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": outsider["user"]["email"]},
            headers=auth_headers(owner["token"]),
        )
        created = await create_team(client, owner["token"], organization_id, "Backend")
        url = f"{teams_url(organization_id)}/{created.json()['id']}/members"
        body = {"user_id": outsider["user"]["id"]}
        await client.post(url, json=body, headers=auth_headers(owner["token"]))

        response = await client.post(url, json=body, headers=auth_headers(owner["token"]))

        assert response.status_code == 409

    async def test_remove_member(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": outsider["user"]["email"]},
            headers=auth_headers(owner["token"]),
        )
        created = await create_team(client, owner["token"], organization_id, "Backend")
        team_id = created.json()["id"]
        await client.post(
            f"{teams_url(organization_id)}/{team_id}/members",
            json={"user_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        removed = await client.delete(
            f"{teams_url(organization_id)}/{team_id}/members/{outsider['user']['id']}",
            headers=auth_headers(owner["token"]),
        )
        read = await client.get(
            f"{teams_url(organization_id)}/{team_id}", headers=auth_headers(owner["token"])
        )

        assert removed.status_code == 204
        assert read.json()["member_ids"] == []

    async def test_removing_someone_who_is_not_a_member_is_reported(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        created = await create_team(client, owner["token"], organization_id, "Backend")

        response = await client.delete(
            f"{teams_url(organization_id)}/{created.json()['id']}/members/{outsider['user']['id']}",
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404


async def register_owner(client: AsyncClient) -> dict[str, Any]:
    from tests.conftest import create_organization, register_user

    session = await register_user(client, prefix="other")
    token = session["access_token"]
    organization = await create_organization(client, token)
    return {"token": token, "user": session["user"], "organization": organization}
