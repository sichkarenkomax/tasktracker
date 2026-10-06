"""Tasks that are not filed under a project.

``project_id`` became nullable so that a new account can record work before it
has created a project - section 30 wants a task list as the home screen, and a
form that demands a project first is not one. These tests pin the three things
that could quietly break: that an unfiled task really works, that the flat create
route is not a way around tenant isolation, and that filing a task is reversible.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def _project(client: AsyncClient, owner: dict[str, Any], name: str = "Apollo") -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": name},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _unfiled(
    client: AsyncClient, owner: dict[str, Any], title: str = "Buy milk"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/tasks",
        params={"organization_id": owner["organization"]["id"]},
        json={"title": title},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


class TestCreateWithoutProject:
    async def test_a_task_needs_no_project(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _unfiled(client, owner)

        assert task["project_id"] is None
        assert task["status"] == "todo"
        assert task["organization_id"] == owner["organization"]["id"]

    async def test_the_organization_is_still_required(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """An unfiled task must not become an organization-less row."""
        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Nowhere to put this"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 201
        assert response.json()["organization_id"] == owner["organization"]["id"]

    async def test_the_flat_route_accepts_a_project(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _project(client, owner)

        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Filed on arrival", "project_id": project_id},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 201, response.text
        assert response.json()["project_id"] == project_id

    async def test_a_project_from_another_tenant_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The flat form must not be a way around the nested route's 404."""
        stranger = await register_user(client, prefix="other")
        theirs = await create_organization(client, stranger["access_token"])
        foreign = await client.post(
            "/api/v1/projects",
            json={"organization_id": theirs["id"], "name": "Theirs"},
            headers=auth_headers(stranger["access_token"]),
        )
        assert foreign.status_code == 201, foreign.text

        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Sneaky", "project_id": foreign.json()["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404

    async def test_the_nested_route_refuses_a_project_in_the_body(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The path is the authority; a body that disagrees is a 422, not a
        silent preference for one of the two."""
        project_id = await _project(client, owner)
        other = await _project(client, owner, "Gemini")

        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Confused", "project_id": other},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422

    async def test_viewer_cannot_create_an_unfiled_task(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": outsider["user"]["email"], "role": "viewer"},
            headers=auth_headers(owner["token"]),
        )

        response = await client.post(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Viewer tries"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestInbox:
    async def test_unfiled_lists_the_tasks_with_no_project(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await _unfiled(client, owner, "Buy milk")
        await _unfiled(client, owner, "Call the dentist")
        project_id = await _project(client, owner)
        await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={"title": "Write the report"},
            headers=headers,
        )

        response = await client.get(
            "/api/v1/tasks",
            params={"organization_id": organization_id, "unfiled": True},
            headers=headers,
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        assert sorted(item["title"] for item in body["items"]) == ["Buy milk", "Call the dentist"]

    async def test_the_whole_list_mixes_filed_and_unfiled(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await _unfiled(client, owner, "Inbox item")
        project_id = await _project(client, owner)
        await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={"title": "Filed"},
            headers=headers,
        )

        body = (
            await client.get(
                "/api/v1/tasks",
                params={"organization_id": organization_id},
                headers=headers,
            )
        ).json()

        assert body["total"] == 2

    async def test_a_project_list_never_contains_unfiled_tasks(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await _unfiled(client, owner, "Inbox item")
        project_id = await _project(client, owner)

        body = (
            await client.get(
                f"/api/v1/projects/{project_id}/tasks",
                params={"organization_id": organization_id},
                headers=headers,
            )
        ).json()

        assert body["total"] == 0


class TestFiling:
    async def test_a_task_can_be_filed_afterwards(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        task = await _unfiled(client, owner)
        project_id = await _project(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"project_id": project_id},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["project_id"] == project_id

    async def test_a_task_can_be_taken_back_out(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        project_id = await _project(client, owner)
        filed = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={"title": "Filed"},
            headers=headers,
        )
        assert filed.status_code == 201, filed.text

        response = await client.patch(
            f"/api/v1/tasks/{filed.json()['id']}",
            params={"organization_id": organization_id},
            json={"project_id": None},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["project_id"] is None

    async def test_omitting_the_key_leaves_the_project_alone(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Same sentinel rule as due_date: absent means "unchanged"."""
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        project_id = await _project(client, owner)
        filed = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={"title": "Filed"},
            headers=headers,
        )

        response = await client.patch(
            f"/api/v1/tasks/{filed.json()['id']}",
            params={"organization_id": organization_id},
            json={"title": "Renamed only"},
            headers=headers,
        )

        assert response.status_code == 200, response.text
        assert response.json()["project_id"] == project_id

    async def test_filing_into_a_foreign_project_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        stranger = await register_user(client, prefix="other")
        theirs = await create_organization(client, stranger["access_token"])
        foreign = await client.post(
            "/api/v1/projects",
            json={"organization_id": theirs["id"], "name": "Theirs"},
            headers=auth_headers(stranger["access_token"]),
        )
        task = await _unfiled(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"project_id": foreign.json()["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404
