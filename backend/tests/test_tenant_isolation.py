"""The tenant boundary, stated as one thing rather than sprinkled through tests.

The product ships with one organization (``SINGLE_ORGANIZATION``), which is a
deliberate choice and not a limitation of the data model: accounts, membership,
tasks and files all carry ``organization_id``, and the test suite runs with the
flag off so the second organization is always buildable.

That combination is where a boundary quietly stops being checked. Every test that
asked "can this member do this?" asked it about *their own* organization, and a
route that loads a record by id and checks the reader - rather than the target -
answers 200 to both. The audit found exactly that on the profile routes. So the
checks are here, in one place, for every route where an id crosses over.

Each test builds two organizations with one reader in each. A boundary that is
only ever tested from one side is not tested.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, create_organization, register_user


async def _tenant(client: AsyncClient, prefix: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """One organization, as ``(holder, member)``.

    ``holder`` owns it and holds the token; ``member`` is an ordinary member of
    the same organization. Built the way the ``owner`` fixture builds one - a
    registered account that then creates an organization - because the boundary
    under test is between organizations, and a tenant that appeared some other
    way would not be the shape the product makes.
    """
    session = await register_user(client, prefix=f"{prefix}_holder")
    organization = await create_organization(client, session["access_token"])
    member = await register_user(client, prefix=f"{prefix}_member")
    joined = await client.post(
        f"/api/v1/organizations/{organization['id']}/members",
        json={"email": member["user"]["email"], "role": "member"},
        headers=auth_headers(session["access_token"]),
    )
    assert joined.status_code == 201, joined.text
    holder = {
        "token": session["access_token"],
        "user": session["user"],
        "organization_id": organization["id"],
    }
    return holder, member


def _headers(token: str) -> dict[str, str]:
    return auth_headers(token)


class TestTheSecondOrganizationIsAlwaysBuildable:
    """The precondition of everything below, and the thing that silently rots.

    ``conftest`` turns ``SINGLE_ORGANIZATION`` off for the rest of the suite,
    which is what keeps the boundary buildable and therefore testable;
    ``test_single_organization`` turns it back on and pins the shipped policy.
    If this test ever fails, one of those two files stopped doing its half, and
    every test in this file is asserting against a shape the product does not
    ship.
    """

    async def test_two_organizations_can_coexist(self, client: AsyncClient) -> None:
        session = await register_user(client, prefix="shape")
        first = await create_organization(client, session["access_token"])
        second = await create_organization(client, session["access_token"])

        listed = await client.get(
            "/api/v1/organizations", headers=_headers(session["access_token"])
        )
        assert first["id"] != second["id"]
        assert {first["id"], second["id"]} <= {row["id"] for row in listed.json()}


class TestAPersonOfOneOrganizationIsNotAPersonOfAnother:
    """The profile routes, which is where the audit found the doors open.

    Both take an id and a name of an organization. Checking the reader is not
    the same as checking the target, and on a single-tenant installation the two
    look identical until somebody installs it twice.
    """

    async def test_the_card_of_a_stranger_is_not_there(self, client: AsyncClient) -> None:
        first, _ = await _tenant(client, "card_a")
        _, stranger = await _tenant(client, "card_b")

        card = await client.get(
            f"/api/v1/users/{stranger['user']['id']}/profile",
            params={"organization_id": first["organization_id"]},
            headers=_headers(first["token"]),
        )

        assert card.status_code == 404, card.text
        assert stranger["user"]["email"] not in card.text

    async def test_neither_is_the_summary(self, client: AsyncClient) -> None:
        first, _ = await _tenant(client, "summ_a")
        _, stranger = await _tenant(client, "summ_b")

        summary = await client.get(
            f"/api/v1/users/{stranger['user']['id']}",
            params={"organization_id": first["organization_id"]},
            headers=_headers(first["token"]),
        )

        assert summary.status_code == 404, summary.text

    async def test_and_not_the_picture_either(self, client: AsyncClient) -> None:
        """The avatar is a file and the file carries its own organization, so
        this one was already correct - which is exactly why it belongs here: a
        right answer that nothing checks is one refactor from a wrong one."""
        first, _ = await _tenant(client, "pic_a")
        _, stranger = await _tenant(client, "pic_b")

        avatar = await client.get(
            f"/api/v1/users/{stranger['user']['id']}/avatar",
            params={"organization_id": first["organization_id"]},
            headers=_headers(first["token"]),
        )

        assert avatar.status_code in (403, 404), avatar.text


class TestAWriteCannotCross:
    """The half that matters more: reading somebody else is embarrassing,
    writing to them is not."""

    async def test_a_team_cannot_take_a_person_from_another_organization(
        self, client: AsyncClient
    ) -> None:
        """The one hole the audit left open.

        Adding somebody to a team checked the reader's permission and never
        checked that the person being added belongs to this organization at all -
        so an administrator of one tenant could write a row naming somebody from
        another into a team that exists only in theirs. No privilege follows, but
        the row is inside the organization and the person is not.
        """
        first, _ = await _tenant(client, "team_a")
        _, stranger = await _tenant(client, "team_b")
        team = await client.post(
            f"/api/v1/organizations/{first['organization_id']}/teams",
            json={"name": "Boundary"},
            headers=_headers(first["token"]),
        )
        assert team.status_code == 201, team.text

        added = await client.post(
            f"/api/v1/organizations/{first['organization_id']}/teams/{team.json()['id']}/members",
            json={"user_id": stranger["user"]["id"]},
            headers=_headers(first["token"]),
        )

        assert added.status_code in (403, 404, 422), added.text
        listed = await client.get(
            f"/api/v1/organizations/{first['organization_id']}/teams/{team.json()['id']}",
            headers=_headers(first["token"]),
        )
        assert stranger["user"]["id"] not in listed.json()["member_ids"]

    async def test_and_a_task_of_one_cannot_be_edited_from_another(
        self, client: AsyncClient
    ) -> None:
        theirs, _ = await _tenant(client, "task_a")
        stranger, _ = await _tenant(client, "task_b")
        task = await client.post(
            "/api/v1/tasks",
            params={"organization_id": theirs["organization_id"]},
            json={"title": "Theirs"},
            headers=_headers(theirs["token"]),
        )
        assert task.status_code == 201, task.text

        edited = await client.patch(
            f"/api/v1/tasks/{task.json()['id']}",
            params={"organization_id": theirs["organization_id"]},
            json={"title": "Renamed by a stranger"},
            headers=_headers(stranger["token"]),
        )

        assert edited.status_code in (403, 404), edited.text
        again = await client.get(
            f"/api/v1/tasks/{task.json()['id']}",
            params={"organization_id": theirs["organization_id"]},
            headers=_headers(theirs["token"]),
        )
        assert again.json()["title"] == "Theirs"

    async def test_and_the_people_list_shows_one_organization(self, client: AsyncClient) -> None:
        """The list is where "somebody is here" is read, so it is where a
        stranger in the roster would be noticed first."""
        first, _ = await _tenant(client, "list_a")
        _, stranger = await _tenant(client, "list_b")

        listed = await client.get(
            f"/api/v1/organizations/{first['organization_id']}/people",
            headers=_headers(first["token"]),
        )
        assert listed.status_code == 200, listed.text
        assert stranger["user"]["id"] not in [row["id"] for row in listed.json()["items"]]
