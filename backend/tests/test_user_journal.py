"""One person's journal (stage 2.11).

The organization feed already reads by time, and by actor as one filter among
others. The journal is the same question with one filter fixed: *what did this
person do here*. Three things make it a separate screen and not a link with
parameters, and they are what these tests hold in place:

* it is read by somebody looking at a colleague, so the person is named in the
  URL and never chosen from a list - there is nothing to mispick;
* the filters are narrower than the feed's, because a journal is a story about
  one person rather than a search over everything;
* and it must stop at the organization boundary like every other screen, even
  though the person being asked about may well exist elsewhere on the
  installation.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def _journal(client: AsyncClient, token: str, organization_id: str, **params: Any) -> Any:
    return await client.get(
        "/api/v1/activity",
        params={"organization_id": organization_id, **params},
        headers=auth_headers(token),
    )


async def _workload(client: AsyncClient, owner: dict[str, Any], other: dict[str, Any]) -> None:
    """Give the two people something different to have done."""
    project = await client.post(
        "/api/v1/projects",
        json={"organization_id": owner["organization"]["id"], "name": "Journal"},
        headers=auth_headers(owner["token"]),
    )
    assert project.status_code == 201, project.text
    for title in ("First", "Second", "Third"):
        await client.post(
            f"/api/v1/projects/{project.json()['id']}/tasks",
            params={"organization_id": owner["organization"]["id"]},
            json={"title": title},
            headers=auth_headers(owner["token"]),
        )
    other_task = await client.post(
        f"/api/v1/projects/{project.json()['id']}/tasks",
        params={"organization_id": owner["organization"]["id"]},
        json={"title": "Theirs"},
        headers=auth_headers(other["token"]),
    )
    assert other_task.status_code == 201, other_task.text


class TestTheJournalOfOnePerson:
    """`actor_id` turns the feed into somebody's history."""

    async def test_it_shows_what_they_did_and_not_what_others_did(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        colleague = await register_user(client, prefix="journal_colleague")
        joined = await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": colleague["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )
        assert joined.status_code == 201, joined.text
        other = {
            "token": colleague["access_token"],
            "user": colleague["user"],
        }
        await _workload(client, owner, other)

        page = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
        )

        assert page.status_code == 200, page.text
        body = page.json()
        assert body["total"] > 0
        assert {row["actor_id"] for row in body["items"]} == {owner["user"]["id"]}
        assert all(row["actor_id"] != other["user"]["id"] for row in body["items"])

    async def test_the_filters_narrow_it(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        await _workload(
            client,
            owner,
            {"token": owner["token"], "user": owner["user"]},
        )

        by_action = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            action="task.created",
        )
        by_entity = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            entity_type="project",
        )
        both = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            entity_type="project",
            action="task.created",
        )

        assert by_action.status_code == 200, by_action.text
        assert all(row["action"] == "task.created" for row in by_action.json()["items"])
        assert all(row["entity_type"] == "project" for row in by_entity.json()["items"])
        assert all(row["entity_type"] == "project" for row in both.json()["items"])
        # Two filters together mean an intersection, not either of them.
        assert both.json()["total"] <= min(by_action.json()["total"], by_entity.json()["total"])

    async def test_a_period_cuts_the_top(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        await _workload(client, owner, {"token": owner["token"], "user": owner["user"]})

        everything = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
        )
        future = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            since=(datetime.now(UTC) + timedelta(days=1)).isoformat(),
        )

        assert everything.json()["total"] > 0
        assert future.json()["items"] == []
        assert future.json()["total"] == 0

    async def test_it_pages(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        await _workload(client, owner, {"token": owner["token"], "user": owner["user"]})

        first = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            limit=2,
        )
        second = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
            limit=2,
            offset=2,
        )

        assert first.json()["total"] == second.json()["total"]
        assert len(first.json()["items"]) == 2
        first_ids = {row["id"] for row in first.json()["items"]}
        second_ids = {row["id"] for row in second.json()["items"]}
        assert not first_ids & second_ids, "a page repeated rows from the previous one"

    async def test_newest_first(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        """A journal read by somebody else is read forwards: what did they do
        last. The projector writes in the order things happened, so a reversed
        order here is a real error and not a matter of taste."""
        await _workload(client, owner, {"token": owner["token"], "user": owner["user"]})

        page = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=owner["user"]["id"],
        )
        stamps = [row["created_at"] for row in page.json()["items"]]

        assert stamps == sorted(stamps, reverse=True)


class TestTheJournalStaysInsideItsOrganization:
    """The person in the URL may exist somewhere else on the installation."""

    async def test_another_tenants_person_is_not_here(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        elsewhere = await create_organization(client, owner["token"], name="Elsewhere")

        page = await _journal(
            client,
            owner["token"],
            owner["organization"]["id"],
            actor_id=elsewhere["id"],
        )

        assert page.status_code == 200, page.text
        assert page.json()["items"] == []
        assert page.json()["total"] == 0
