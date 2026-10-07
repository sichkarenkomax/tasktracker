"""Tasks: CRUD, tenant isolation and permissions.

The module is exercised through HTTP only. Everything it does - filtering,
sorting, tenant scoping, event publication - is observable from the API, and a
test that reached past the router would pass even if the route checked nothing.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def _project(
    client: AsyncClient, owner: dict[str, Any], name: str = "Apollo"
) -> dict[str, Any]:
    response = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": name},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _task(
    client: AsyncClient,
    owner: dict[str, Any],
    *,
    project_id: str | None = None,
    title: str = "Prepare report",
    **extra: Any,
) -> dict[str, Any]:
    project_id = project_id or (await _project(client, owner))["id"]
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        params={"organization_id": owner["organization"]["id"]},
        json={"title": title, **extra},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _add_member(
    client: AsyncClient,
    owner: dict[str, Any],
    invitee: dict[str, Any],
    role: str = "member",
) -> None:
    response = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": invitee["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text


class TestCreate:
    async def test_defaults(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(client, owner)

        assert task["status"] == "todo"
        assert task["priority"] == "medium"
        assert task["due_date"] is None
        assert task["completed_at"] is None
        assert task["creator_id"] == owner["user"]["id"]
        assert task["organization_id"] == owner["organization"]["id"]

    async def test_the_creator_becomes_the_responsible_person(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Nobody named a responsible person, and the column forbids that.

        Falling back to the creator is the only answer available at that moment,
        and it keeps a client from having to ask "who is this for?" before it can
        save anything.
        """
        task = await _task(client, owner)

        assert task["assignee_id"] == owner["user"]["id"]

    async def test_a_named_responsible_person_is_kept(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await _add_member(client, owner, outsider)
        project_id = (await _project(client, owner))["id"]

        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Handed over", "assignee_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 201, response.text
        assert response.json()["assignee_id"] == outsider["user"]["id"]

    async def test_blank_title_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = (await _project(client, owner))["id"]

        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "   "},
            headers=auth_headers(owner["token"]),
        )

        # The schema only knows the string is non-empty; emptiness after
        # stripping is the service's business rule and arrives as a 422.
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_outsider_cannot_create(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        project_id = (await _project(client, owner))["id"]

        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Sneaky"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_unknown_project_is_404(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        response = await client.post(
            "/api/v1/projects/6f9c8b7a-0000-0000-0000-000000000000/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Orphan"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404

    async def test_assignee_must_be_a_member(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Assigning to an outsider is a bad value, not a forbidden action."""
        project_id = (await _project(client, owner))["id"]

        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Assigned", "assignee_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422


class TestRead:
    async def test_list_is_scoped_to_the_project(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        first = await _project(client, owner, "Apollo")
        second = await _project(client, owner, "Gemini")
        await _task(client, owner, project_id=first["id"], title="One")
        await _task(client, owner, project_id=second["id"], title="Two")

        response = await client.get(
            f"/api/v1/projects/{first['id']}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert [item["title"] for item in body["items"]] == ["One"]
        assert body["total"] == 1

    async def test_a_task_from_another_tenant_is_invisible(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        other_session = await register_user(client, prefix="other")
        other_token = other_session["access_token"]
        other_org = await create_organization(client, other_token, name="Other")
        other_project = await client.post(
            "/api/v1/projects",
            json={"organization_id": other_org["id"], "name": "Theirs"},
            headers=auth_headers(other_token),
        )
        secret = await client.post(
            f"/api/v1/projects/{other_project.json()['id']}/tasks",
            params={"organization_id": other_org["id"]},
            json={"title": "Secret"},
            headers=auth_headers(other_token),
        )
        assert secret.status_code == 201

        lookup = await client.get(
            f"/api/v1/tasks/{secret.json()['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        listing = await client.get(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert lookup.status_code == 404
        assert listing.json()["items"] == []

    async def test_pagination_reports_the_unfiltered_total(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = (await _project(client, owner))["id"]
        for index in range(3):
            await _task(client, owner, project_id=project_id, title=f"Task {index}")

        response = await client.get(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": owner["organization"]["id"], "limit": 2, "offset": 0},
            headers=auth_headers(owner["token"]),
        )

        body = response.json()
        assert len(body["items"]) == 2
        assert body["total"] == 3

    async def test_pages_do_not_overlap(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        """Every task is written within the same millisecond, so only the id
        tie-breaker in the ORDER BY keeps the two pages disjoint."""
        project_id = (await _project(client, owner))["id"]
        created = {
            (await _task(client, owner, project_id=project_id, title=f"Task {index}"))["id"]
            for index in range(6)
        }

        params = {"organization_id": owner["organization"]["id"], "limit": 3}
        pages = []
        for offset in (0, 3):
            response = await client.get(
                f"/api/v1/projects/{project_id}/tasks",
                params={**params, "offset": offset},
                headers=auth_headers(owner["token"]),
            )
            pages.append([item["id"] for item in response.json()["items"]])

        assert not set(pages[0]) & set(pages[1])
        assert set(pages[0]) | set(pages[1]) == created

    async def test_unknown_sort_field_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A mistyped sort must be a 422, not a silently ignored parameter."""
        response = await client.get(
            "/api/v1/tasks",
            params={"organization_id": owner["organization"]["id"], "sort": "priorty"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422


class TestUpdate:
    async def test_status_transition_sets_completed_at(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]

        done = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "done"},
            headers=auth_headers(owner["token"]),
        )

        assert done.status_code == 200
        assert done.json()["status"] == "done"
        assert done.json()["completed_at"] is not None

    async def test_reopening_clears_completed_at(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "done"},
            headers=headers,
        )

        reopened = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "todo"},
            headers=headers,
        )

        assert reopened.json()["completed_at"] is None

    async def test_omitting_due_date_keeps_it(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner, due_date="2030-01-31")
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])

        renamed = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"title": "Renamed"},
            headers=headers,
        )
        cleared = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"due_date": None},
            headers=headers,
        )

        assert renamed.json()["due_date"] == "2030-01-31"
        assert cleared.json()["due_date"] is None

    async def test_viewer_cannot_update(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        await _add_member(client, owner, outsider, role="viewer")

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Hijacked"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_member_can_assign(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        await _add_member(client, owner, outsider)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"assignee_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["assignee_id"] == outsider["user"]["id"]

    async def test_reassignment_to_an_outsider_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)

        response = await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"assignee_id": outsider["user"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422


class TestDelete:
    async def test_member_cannot_delete(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        await _add_member(client, owner, outsider)

        response = await client.delete(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_admin_can_delete(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        await _add_member(client, owner, outsider, role="admin")
        organization_id = owner["organization"]["id"]

        deleted = await client.delete(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            headers=auth_headers(outsider["token"]),
        )
        listed = await client.get(
            "/api/v1/tasks",
            params={"organization_id": organization_id},
            headers=auth_headers(owner["token"]),
        )

        assert deleted.status_code == 204
        assert listed.json()["items"] == []

    async def test_deleting_a_task_takes_its_comments_with_it(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": organization_id},
            json={"content": "Doomed"},
            headers=headers,
        )

        await client.delete(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            headers=headers,
        )
        listed = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": organization_id},
            headers=headers,
        )

        assert listed.status_code == 404
