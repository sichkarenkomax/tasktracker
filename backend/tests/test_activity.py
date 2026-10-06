"""Activity feed.

Activity is written by a wildcard Event Bus subscriber, never by the routers
(docs/architecture.md, sections 19 and 21). The tests therefore check the two
properties that matter: every domain event shows up without Core knowing what
produced it, and the feed never crosses the organization boundary.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def feed(client: AsyncClient, token: str, organization_id: str, **params: Any) -> Any:
    return await client.get(
        "/api/v1/activity",
        params={"organization_id": organization_id, **params},
        headers=auth_headers(token),
    )


async def make_project(client: AsyncClient, owner: dict[str, Any], name: str) -> str:
    response = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": name},
        headers=auth_headers(owner["token"]),
    )
    assert response.status_code == 201, response.text
    project_id: str = response.json()["id"]
    return project_id


async def other_owner(client: AsyncClient) -> dict[str, Any]:
    session = await register_user(client, prefix="other")
    token = session["access_token"]
    return {
        "token": token,
        "user": session["user"],
        "organization": await create_organization(client, token),
    }


class TestProjection:
    async def test_project_lifecycle_is_recorded(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await make_project(client, owner, "Apollo")

        response = await feed(client, owner["token"], owner["organization"]["id"])

        body = response.json()
        assert response.status_code == 200
        actions = [item["action"] for item in body["items"]]
        assert "project.created" in actions
        assert body["total"] == len(actions)

        created = next(item for item in body["items"] if item["action"] == "project.created")
        assert created["entity_type"] == "project"
        assert created["entity_id"] == project_id
        assert created["actor_id"] == owner["user"]["id"]
        assert created["organization_id"] == owner["organization"]["id"]

    async def test_updates_and_deletions_are_recorded(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        project_id = await make_project(client, owner, "Apollo")
        await client.patch(
            f"/api/v1/projects/{project_id}",
            params={"organization_id": organization_id},
            json={"status": "active"},
            headers=auth_headers(owner["token"]),
        )
        await client.delete(
            f"/api/v1/projects/{project_id}",
            params={"organization_id": organization_id},
            headers=auth_headers(owner["token"]),
        )

        actions = [
            item["action"]
            for item in (await feed(client, owner["token"], organization_id)).json()["items"]
        ]

        assert "project.updated" in actions
        assert "project.deleted" in actions

    async def test_membership_changes_are_recorded(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": outsider["user"]["email"]},
            headers=auth_headers(owner["token"]),
        )

        actions = [
            item["action"]
            for item in (await feed(client, owner["token"], owner["organization"]["id"])).json()[
                "items"
            ]
        ]

        assert "organization.member_added" in actions

    async def test_logins_are_excluded(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        """Logging in is noise, not history."""
        await client.post(
            "/api/v1/auth/login",
            json={"login": owner["user"]["email"], "password": "sup3r-secret"},
        )

        body = (await feed(client, owner["token"], owner["organization"]["id"])).json()

        assert "user.logged_in" not in [item["action"] for item in body["items"]]

    async def test_every_line_of_the_feed_is_readable(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """No row may be a bare event name.

        The feed is the only history a team has, and Activity renders one line per
        event. A row without a summary shows `project.created` to the reader, which
        is a database value leaking into the product. Core writes the sentence for
        its own events, and every module writes one for its own; this is the test
        that says so.
        """
        organization_id = owner["organization"]["id"]
        await make_project(client, owner, "Apollo")
        gemini_id = await make_project(client, owner, "Gemini")
        await client.patch(
            f"/api/v1/projects/{gemini_id}",
            params={"organization_id": organization_id},
            json={"description": "Changed"},
            headers=auth_headers(owner["token"]),
        )
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": outsider["user"]["email"]},
            headers=auth_headers(owner["token"]),
        )
        await client.post(
            f"/api/v1/organizations/{organization_id}/teams",
            json={"name": "Backend"},
            headers=auth_headers(owner["token"]),
        )

        body = (await feed(client, owner["token"], organization_id)).json()

        # Guard the guard: without this, a typo in the setup above would leave the
        # feed short and the assertion would pass for the wrong reason.
        actions = {item["action"] for item in body["items"]}
        assert {
            "organization.created",
            "project.created",
            "project.updated",
            "organization.member_added",
            "team.created",
        } <= actions, f"setup produced only {sorted(actions)}"

        unreadable = [item["action"] for item in body["items"] if not item["summary"]]
        assert unreadable == [], f"feed rows without a summary: {unreadable}"
        # And a summary must be a sentence, not a repeat of the action name.
        assert all(item["summary"] != item["action"] for item in body["items"]), (
            "a summary that only restates the action adds nothing"
        )

    async def test_platform_events_are_not_attributed_to_any_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """`user.registered` happened before any organization existed."""
        await register_user(client, prefix="newcomer")

        for organization_id in (owner["organization"]["id"],):
            body = (await feed(client, owner["token"], organization_id)).json()
            assert "user.registered" not in [item["action"] for item in body["items"]]


class TestIsolation:
    async def test_the_feed_never_crosses_organizations(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        theirs = await other_owner(client)
        await make_project(client, owner, "Mine")
        await make_project(client, theirs, "Theirs")

        mine = (
            await feed(
                client, owner["token"], owner["organization"]["id"], action="project.created"
            )
        ).json()
        theirs_body = (
            await feed(
                client,
                theirs["token"],
                theirs["organization"]["id"],
                action="project.created",
            )
        ).json()

        assert [item["payload"]["name"] for item in mine["items"]] == ["Mine"]
        assert [item["payload"]["name"] for item in theirs_body["items"]] == ["Theirs"]
        assert mine["items"][0]["organization_id"] == owner["organization"]["id"]
        assert theirs_body["items"][0]["organization_id"] == theirs["organization"]["id"]

    async def test_a_non_member_cannot_read_the_feed(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await feed(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 403


class TestRollbackSafety:
    """A rejected operation must not leave a trace in the feed.

    Events are buffered until the transaction commits, so a 4xx response - for
    example a conflicting name - must produce no activity at all.
    """

    async def test_a_rejected_create_writes_nothing(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await make_project(client, owner, "Apollo")

        rejected = await client.post(
            "/api/v1/projects",
            json={"organization_id": organization_id, "name": "Apollo"},
            headers=auth_headers(owner["token"]),
        )
        body = (
            await feed(client, owner["token"], organization_id, action="project.created")
        ).json()

        assert rejected.status_code == 409
        assert body["total"] == 1

    async def test_a_failed_authorization_writes_nothing(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.post(
            "/api/v1/projects",
            json={"organization_id": owner["organization"]["id"], "name": "Sneaky"},
            headers=auth_headers(outsider["token"]),
        )

        assert response.status_code == 403
        # The outsider created nothing, and the owner's feed is unaffected.
        owner_feed = (await feed(client, owner["token"], owner["organization"]["id"])).json()
        assert "project.created" not in [item["action"] for item in owner_feed["items"]]


class TestFilters:
    async def test_by_entity(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await make_project(client, owner, "Apollo")
        await make_project(client, owner, "Gemini")

        response = await client.get(
            f"/api/v1/activity/entity/project/{project_id}",
            params={"organization_id": owner["organization"]["id"]},
            headers=auth_headers(owner["token"]),
        )

        body = response.json()
        assert body["total"] == 1
        assert body["items"][0]["entity_id"] == project_id

    async def test_by_action(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        await make_project(client, owner, "Apollo")
        await make_project(client, owner, "Gemini")

        body = (
            await feed(
                client, owner["token"], owner["organization"]["id"], action="project.created"
            )
        ).json()

        assert body["total"] == 2

    async def test_unknown_action_yields_nothing(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await make_project(client, owner, "Apollo")

        body = (
            await feed(client, owner["token"], owner["organization"]["id"], action="nope.nope")
        ).json()

        assert body["total"] == 0
        assert body["items"] == []

    async def test_total_ignores_paging_but_items_do_not(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        for name in ("Alpha", "Beta", "Gamma"):
            await make_project(client, owner, name)

        body = (
            await feed(
                client,
                owner["token"],
                owner["organization"]["id"],
                action="project.created",
                limit=2,
                offset=1,
            )
        ).json()

        assert body["total"] == 3
        assert [item["payload"]["name"] for item in body["items"]] == ["Beta", "Alpha"]
        assert body["limit"] == 2
        assert body["offset"] == 1

    async def test_newest_first(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        for name in ("Alpha", "Beta", "Gamma"):
            await make_project(client, owner, name)

        body = (
            await feed(
                client,
                owner["token"],
                owner["organization"]["id"],
                action="project.created",
            )
        ).json()

        names = [item["payload"]["name"] for item in body["items"]]
        assert names == ["Gamma", "Beta", "Alpha"]
