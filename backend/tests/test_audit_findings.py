"""What the audit found, kept as tests (stage 2.23).

Three of the findings of the intermediate audit were not "the code could be
cleaner" but "the code lets somebody do something they must not". Each test here
failed before the fix and exists to make the failure impossible to reintroduce
quietly. The story of why they exist is in ``docs/audit-report.md``; the tests
themselves say only what is wrong without the code being wrong.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, register_user


async def _join(
    client: AsyncClient, owner: dict[str, Any], prefix: str, role: str = "member"
) -> dict[str, Any]:
    session = await register_user(client, prefix=prefix)
    added = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": session["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert added.status_code == 201, added.text
    return {"token": session["access_token"], "user": session["user"], "role": role}


def _headers(token: str) -> dict[str, str]:
    return auth_headers(token)


class TestEveryFieldOfTheEditorIsGuarded:
    """`AdminUserUpdate` has eleven fields and, for a while, one guard fewer.

    The router checks permission per field, and the fields it checks are the ones
    written in an `if`. `birthday` was written in an `if` too - after the last
    permission check - so the one field a plain member could write into someone
    else's record was the one nobody thought to guard.
    """

    async def test_a_member_cannot_set_a_birthday(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "birthday")

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={"birthday": "1990-01-01"},
            headers=_headers(await _member_token(client, owner)),
        )

        assert response.status_code == 403
        assert "user.update" in response.text

    async def test_and_the_birthday_is_actually_unchanged(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "birthday2")
        await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={"birthday": "1975-06-06"},
            headers=_headers(owner["token"]),
        )

        await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={"birthday": "1990-01-01"},
            headers=_headers(await _member_token(client, owner)),
        )

        card = await client.get(
            f"/api/v1/users/{person['user']['id']}/profile",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(owner["token"]),
        )
        assert card.json()["birthday"] == "1975-06-06"


async def _member_token(client: AsyncClient, owner: dict[str, Any]) -> str:
    """An ordinary member of this organization - the rank with the fewest rights.

    A stranger would be refused for the wrong reason (not a member at all), and
    an administrator would be refused for the right one, so the test has to stand
    exactly where the hole was.
    """
    member = await _join(client, owner, "editor_member", role="member")
    return member["token"]


class TestATenantIsNotAnAddress:
    """`GET /users/{id}` and `/profile` took any account on the installation.

    Both routes checked that the *reader* was a member of the organization named
    in the query, then loaded the *target* by id alone. On an installation with
    one tenant that reads as an oversight; on a second tenant it is the whole
    tenant boundary, walked through by anyone who can guess a UUID.
    """

    async def test_a_member_cannot_read_a_person_outside_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        reader = await _join(client, owner, "reader")
        # Registered but never added: an account of this installation that this
        # organization has nothing to do with.
        stranger = await register_user(client, prefix="stranger")

        card = await client.get(
            f"/api/v1/users/{stranger['user']['id']}/profile",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(reader["token"]),
        )
        summary = await client.get(
            f"/api/v1/users/{stranger['user']['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(reader["token"]),
        )

        assert card.status_code == 404, card.text
        assert summary.status_code == 404, summary.text
        assert stranger["user"]["email"] not in card.text

    async def test_an_administrator_cannot_either(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The privilege is the organization's, not the role's.

        An administrator reads the people of *their* organization. Somebody from
        another one is not theirs to read, which is the whole point of the role.
        """
        stranger = await register_user(client, prefix="admin_stranger")

        card = await client.get(
            f"/api/v1/users/{stranger['user']['id']}/profile",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(owner["token"]),
        )

        assert card.status_code == 404, card.text

    async def test_a_member_of_the_organization_is_still_readable(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The refusal is about membership, not about the reader being a member.

        Otherwise the fix would be indistinguishable from "the profile endpoint
        stopped working", which is how a right thing becomes a wrong one.
        """
        person = await _join(client, owner, "colleague")
        reader = await _join(client, owner, "peer")

        card = await client.get(
            f"/api/v1/users/{person['user']['id']}/profile",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(reader["token"]),
        )

        assert card.status_code == 200, card.text
        assert card.json()["username"] == person["user"]["username"]


class TestTheDirectoryRouteRespectsTheSameChoice:
    """`GET /users/{id}` bypassed stage 2.6 while `/profile` honoured it.

    A person who answered "administrators only" had their profile blanked by one
    route and served in full by the other, in the same second. Two routes, two
    answers to one question - which is the shape the bug took.
    """

    async def test_the_summary_hides_the_address_a_person_withdrew(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "withdrawn")
        reader = await _join(client, owner, "nosy")

        chosen = await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": owner["organization"]["id"]},
            json={"values": {"contacts_visibility": "admins"}},
            headers=_headers(person["token"]),
        )
        assert chosen.status_code == 200, chosen.text

        summary = await client.get(
            f"/api/v1/users/{person['user']['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(reader["token"]),
        )

        assert summary.status_code == 200, summary.text
        assert summary.json()["email"] is None, "the address came out of the other door"

    async def test_and_an_administrator_still_reads_it(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "withdrawn2")
        await client.put(
            "/api/v1/users/me/settings",
            params={"organization_id": owner["organization"]["id"]},
            json={"values": {"contacts_visibility": "admins"}},
            headers=_headers(person["token"]),
        )

        summary = await client.get(
            f"/api/v1/users/{person['user']['id']}",
            params={"organization_id": owner["organization"]["id"]},
            headers=_headers(owner["token"]),
        )

        assert summary.status_code == 200, summary.text
        assert summary.json()["email"] == person["user"]["email"]
