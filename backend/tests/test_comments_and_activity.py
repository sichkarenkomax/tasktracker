"""Comments and the Activity feed.

These two are the same test file on purpose. A comment is the module's simplest
write, and the feed it produces is the platform's proof that Core can observe a
module it knows nothing about (docs/architecture.md, sections 18, 19, 21).
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers


async def _project(client: AsyncClient, owner: dict[str, Any]) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": "Apollo"},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


async def _task(
    client: AsyncClient, owner: dict[str, Any], *, title: str = "Prepare report"
) -> dict[str, Any]:
    project_id = await _project(client, owner)
    response = await client.post(
        f"/api/v1/projects/{project_id}/tasks",
        params={"organization_id": owner["organization"]["id"]},
        json={"title": title},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response.json()


async def _comment(
    client: AsyncClient,
    owner: dict[str, Any],
    task_id: str,
    content: str = "Looks good to me",
) -> Any:
    response = await client.post(
        f"/api/v1/tasks/{task_id}/comments",
        params={"organization_id": owner["organization"]["id"]},
        json={"content": content},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    return response


async def _activity(
    client: AsyncClient, owner: dict[str, Any], **params: Any
) -> list[dict[str, Any]]:
    response = await client.get(
        "/api/v1/activity",
        params={"organization_id": owner["organization"]["id"], **params},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 200, response.text
    body = response.json()
    items: list[dict[str, Any]] = body["items"]
    return items


class TestComments:
    async def test_write_and_read(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(client, owner)

        first = await _comment(client, owner, task["id"], "First")
        second = await _comment(client, owner, task["id"], "Second")

        response = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["total"] == 2
        # Oldest first: a comment thread read top-down is a conversation, and
        # the reverse is the same information in a form nobody can follow.
        assert [item["content"] for item in body["items"]] == ["First", "Second"]
        assert [item["id"] for item in body["items"]] == [first.json()["id"], second.json()["id"]]
        assert all(item["author_id"] == owner["user"]["id"] for item in body["items"])

    async def test_content_is_trimmed(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(client, owner)

        await _comment(client, owner, task["id"], "   padded   ")

        response = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.json()["items"][0]["content"] == "padded"

    async def test_blank_comment_is_rejected(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)

        response = await client.post(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": owner["organization"]["id"]},
            json={"content": "    "},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 422
        assert response.json()["error"]["code"] == "validation_error"

    async def test_comments_of_a_foreign_task_are_invisible(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)

        response = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403

    async def test_author_removes_their_own_comment(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        comment = (await _comment(client, owner, task["id"])).json()

        response = await client.delete(
            f"/api/v1/tasks/{task['id']}/comments/{comment['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )
        listed = await client.get(
            f"/api/v1/tasks/{task['id']}/comments",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 204
        assert listed.json()["items"] == []

    async def test_somebody_else_needs_delete_rights(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        comment = (await _comment(client, owner, task["id"])).json()
        organization_id = owner["organization"]["id"]
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": outsider["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )

        response = await client.delete(
            f"/api/v1/tasks/{task['id']}/comments/{comment['id']}",
            params={"organization_id": organization_id},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestActivity:
    async def test_task_lifecycle_reaches_the_feed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "in_progress"},
            headers=headers,
        )
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "done"},
            headers=headers,
        )

        actions = [item["action"] for item in await _activity(client, owner)]

        assert "task.created" in actions
        assert "task.status_changed" in actions
        assert "task.completed" in actions

    async def test_reopening_is_reported(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        headers = auth_headers(owner["token"])
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "done"},
            headers=headers,
        )
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "todo"},
            headers=headers,
        )

        actions = [item["action"] for item in await _activity(client, owner)]

        assert "task.reopened" in actions

    async def test_one_action_reads_as_one_line(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A status change must not produce two feed lines saying the same thing.

        ``task.status_changed`` reports what moved and from what to what;
        ``task.updated`` is the aggregate event for consumers that only need to
        know *something* changed. Showing both leaves a reader parsing a duplicate
        on the single most common action in the product.
        """
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "in_progress"},
            headers=auth_headers(owner["token"]),
        )

        actions = [item["action"] for item in await _activity(client, owner)]

        assert actions.count("task.status_changed") == 1
        assert "task.updated" not in actions

    async def test_a_field_without_its_own_event_still_reaches_the_feed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Renaming has no dedicated event, so the aggregate one must show up."""
        task = await _task(client, owner)
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": "Prepare the report"},
            headers=auth_headers(owner["token"]),
        )

        items = await _activity(client, owner)

        assert "task.updated" in [item["action"] for item in items]
        updated = next(item for item in items if item["action"] == "task.updated")
        assert "title" in updated["payload"]["changes"]["fields"]
        assert "Prepare the report" in updated["summary"]

    async def test_a_comment_is_attached_to_its_task(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The task page asks the feed by entity, so the reference must be the
        task and not the comment."""
        task = await _task(client, owner)
        await _comment(client, owner, task["id"])

        items = await _activity(client, owner, entity_type="task", entity_id=task["id"])

        assert "comment.created" in [item["action"] for item in items]

    async def test_the_feed_reads_like_a_story(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Section 19 wants text a human can read, not a list of enum changes."""
        task = await _task(client, owner)
        organization_id = owner["organization"]["id"]
        await client.patch(
            f"/api/v1/tasks/{task['id']}",
            params={"organization_id": organization_id},
            json={"status": "done"},
            headers=auth_headers(owner["token"]),
        )

        items = await _activity(client, owner, entity_id=task["id"])
        by_action = {item["action"]: item["summary"] for item in items}

        assert by_action["task.completed"] == "completed task 'Prepare report'"
        assert (
            by_action["task.status_changed"] == "changed status of 'Prepare report': todo -> done"
        )
        assert all(item["summary"] for item in items), "every feed line must be readable"
        assert all(item["actor_id"] == owner["user"]["id"] for item in items)
