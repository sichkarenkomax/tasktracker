"""Task list: filtering, sorting, search and pagination.

Section 30 asks for a list with search, filtering, sorting, creation, editing
and deletion. This file covers everything that happens *to* the list rather than
to one task, because those code paths are shared by every view the product will
ever grow (Kanban, Gantt, Scrum all reuse them).
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers

TODAY = date.today()


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


#: ``(title, priority, due_date, status)``. ``status`` is applied with a PATCH
#: rather than in the create body: a task is always born ``todo``, and the write
#: schemas reject unknown fields, so a fixture that tried to set it up front
#: would get a 422 rather than the mixture of states it needs.
FIXTURE: list[tuple[str, str, str | None, str]] = [
    ("Write the quarterly report", "urgent", None, "todo"),
    ("Fix the login redirect", "high", None, "in_progress"),
    ("Tidy the backlog", "low", None, "todo"),
    ("Ship the release notes", "medium", str(TODAY - timedelta(days=3)), "done"),
    ("Book the venue", "medium", str(TODAY + timedelta(days=7)), "todo"),
]


async def _seed(client: AsyncClient, owner: dict[str, Any]) -> str:
    """A small, deliberately varied set of tasks. Returns the project id."""
    project_id = (await _project(client, owner))["id"]
    organization_id = owner["organization"]["id"]
    for title, priority, due_date, status in FIXTURE:
        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={"title": title, "priority": priority, "due_date": due_date},
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 201, response.text
        moved = await client.patch(
            f"/api/v1/tasks/{response.json()['id']}",
            params={"organization_id": organization_id},
            json={"status": status},
            headers=auth_headers(owner["token"]),
        )
        assert moved.status_code == 200, moved.text
    return project_id


async def _list(
    client: AsyncClient,
    owner: dict[str, Any],
    *,
    project_id: str | None = None,
    **params: Any,
) -> dict[str, Any]:
    query: dict[str, Any] = {"organization_id": owner["organization"]["id"], **params}
    if project_id is None:
        response = await client.get(
            "/api/v1/tasks", params=query, headers=auth_headers(owner["token"])
        )
    else:
        response = await client.get(
            f"/api/v1/projects/{project_id}/tasks",
            params=query,
            headers=auth_headers(owner["token"]),
        )
    assert response.status_code == 200, response.text
    return response.json()


def _titles(page: dict[str, Any]) -> list[str]:
    return [item["title"] for item in page["items"]]


class TestFiltering:
    async def test_by_status(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, status=["todo"])

        assert sorted(_titles(page)) == [
            "Book the venue",
            "Tidy the backlog",
            "Write the quarterly report",
        ]
        assert page["total"] == 3

    async def test_by_several_statuses(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, status=["done", "in_progress"])

        assert sorted(_titles(page)) == ["Fix the login redirect", "Ship the release notes"]

    async def test_by_priority(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, priority=["urgent", "high"])

        assert sorted(_titles(page)) == ["Fix the login redirect", "Write the quarterly report"]

    async def test_by_assignee(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        await _seed(client, owner)

        page = await _list(client, owner, assignee_id=owner["user"]["id"])

        # Nothing in the fixture is assigned, so filtering by anybody returns
        # nothing - which is exactly the "my tasks" view on day one.
        assert page["items"] == []

    async def test_unassigned(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, unassigned=True)

        assert page["total"] == 5

    async def test_overdue_excludes_finished_work(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A deadline that passed on a task which is already done is history."""
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, overdue=True)

        assert page["items"] == []

    async def test_overdue_finds_open_work(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = (await _project(client, owner, "Gemini"))["id"]
        organization_id = owner["organization"]["id"]
        response = await client.post(
            f"/api/v1/projects/{project_id}/tasks",
            params={"organization_id": organization_id},
            json={
                "title": "Chase the invoice",
                "due_date": str(TODAY - timedelta(days=1)),
            },
            headers=auth_headers(owner["token"]),
        )
        assert response.status_code == 201, response.text

        page = await _list(client, owner, project_id=project_id, overdue=True)

        assert _titles(page) == ["Chase the invoice"]

    async def test_due_date_range(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, due_to=str(TODAY))

        assert _titles(page) == ["Ship the release notes"]

    async def test_filters_combine(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(
            client, owner, project_id=project_id, status=["todo"], priority=["urgent", "low"]
        )

        assert sorted(_titles(page)) == ["Tidy the backlog", "Write the quarterly report"]

    async def test_total_reflects_the_filters(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A count taken from a different filter set is the classic off-by-page."""
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, status=["todo"], limit=1)

        assert len(page["items"]) == 1
        assert page["total"] == 3


class TestSorting:
    async def test_priority_is_ordered_by_meaning_not_alphabet(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Alphabetically "high" < "low" < "medium" < "urgent", which is nonsense."""
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, sort="priority", direction="asc")

        # Only the ranks are asserted: the two ``medium`` tasks tie, and the id
        # tie-breaker between them is not something a test should pin down.
        assert [item["priority"] for item in page["items"]] == [
            "low",
            "medium",
            "medium",
            "high",
            "urgent",
        ]
        assert _titles(page)[0] == "Tidy the backlog"
        assert _titles(page)[-1] == "Write the quarterly report"

    async def test_priority_descending(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, sort="priority", direction="desc")

        assert page["items"][0]["priority"] == "urgent"

    async def test_status_follows_the_workflow(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, sort="status", direction="asc")

        assert [item["status"] for item in page["items"]] == [
            "todo",
            "todo",
            "todo",
            "in_progress",
            "done",
        ]

    async def test_title(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, sort="title", direction="asc")

        assert _titles(page) == sorted(_titles(page))

    async def test_due_date_sinks_tasks_without_a_deadline(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """An empty cell at the top of a deadline list reads as urgency."""
        project_id = await _seed(client, owner)

        ascending = await _list(
            client, owner, project_id=project_id, sort="due_date", direction="asc"
        )
        descending = await _list(
            client, owner, project_id=project_id, sort="due_date", direction="desc"
        )

        assert ascending["items"][0]["due_date"] == str(TODAY - timedelta(days=3))
        assert descending["items"][0]["due_date"] == str(TODAY + timedelta(days=7))
        assert ascending["items"][-1]["due_date"] is None
        assert descending["items"][-1]["due_date"] is None

    async def test_default_is_newest_first(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id)

        assert page["sort"] == "created_at"
        assert page["direction"] == "desc"
        # Newest first, so the task seeded last leads.
        assert _titles(page)[0] == "Book the venue"


class TestSearch:
    async def test_matches_a_substring_of_the_title(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, search="report")

        assert _titles(page) == ["Write the quarterly report"]

    async def test_is_case_insensitive(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, search="RELEASE")

        assert _titles(page) == ["Ship the release notes"]

    async def test_several_tokens_must_all_match(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _seed(client, owner)

        both = await _list(client, owner, project_id=project_id, search="the venue")
        only_one = await _list(client, owner, project_id=project_id, search="the nonsense")

        assert _titles(both) == ["Book the venue"]
        assert only_one["items"] == []

    async def test_wildcards_in_the_query_are_literal(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Without escaping, ``%`` would match every row in the table."""
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, search="%")

        assert page["items"] == []

    async def test_search_combines_with_filters(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, search="the", status=["todo"])

        assert sorted(_titles(page)) == [
            "Book the venue",
            "Tidy the backlog",
            "Write the quarterly report",
        ]


class TestPagination:
    async def test_limit_is_clamped_to_the_maximum(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A mistyped limit must not become a 422 on an otherwise valid request."""
        project_id = await _seed(client, owner)

        page = await _list(client, owner, project_id=project_id, limit=100_000)

        assert page["limit"] == 100
        assert page["total"] == 5
