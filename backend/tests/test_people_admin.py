"""The merged people list and the administrator's editor (stages 2.17, 2.18).

Two screens used to be here and are now one: a roster of this organization's
members, and a directory of every account on the installation. The tests below
pin the properties that made the merge worth doing and the one that made it
risky:

* the tenant boundary survives - a plain member gets this organization's
  people, and asking for the installation's other accounts is a refusal rather
  than an empty page (2.17);
* sorting, filtering and paging agree with each other, including the count in
  the footer, because a table that says "1-50 of 178" and then shows 12 rows is
  worse than no table;
* a contact hidden by stage 2.6 stays hidden here - the merged table is a new
  place to leak an address, and a new place is exactly how that happens;
* the editor (2.18) checks every permission before writing anything, so a
  refused half of a form leaves the person as they were.
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


async def _people(client: AsyncClient, token: str, organization_id: str, **query: Any) -> Any:
    parts = "&".join(f"{key}={value}" for key, value in query.items() if value is not None)
    url = f"/api/v1/organizations/{organization_id}/people"
    if parts:
        url += f"?{parts}"
    return await client.get(url, headers=_headers(token))


class TestPeopleList:
    """One list of people (stage 2.17)."""

    async def test_an_ordinary_member_sees_the_organizations_people(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        colleague = await _join(client, owner, "colleague")
        # An account that exists on the installation but belongs to nobody here.
        outsider = await register_user(client, prefix="outsider")

        response = await _people(client, colleague["token"], owner["organization"]["id"])

        assert response.status_code == 200, response.text
        body = response.json()
        usernames = {row["username"] for row in body["items"]}
        assert colleague["user"]["username"] in usernames
        assert owner["user"]["username"] in usernames
        # The default scope is "members", and somebody who is not one is not in
        # this organization's answer at all.
        assert outsider["user"]["username"] not in usernames
        assert all(row["in_organization"] for row in body["items"])

    async def test_asking_for_the_installation_is_refused_for_an_ordinary_member(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A directory that crosses the tenant boundary is a leak with a filter.

        Answering with an empty page instead of a refusal would look like "this
        organization has nobody else", which is a different and wrong statement.
        """
        colleague = await _join(client, owner, "colleague")

        response = await _people(
            client, colleague["token"], owner["organization"]["id"], scope="all"
        )

        assert response.status_code == 403
        assert "portal administrator" in response.json()["error"]["message"]

    async def test_a_superuser_sees_the_accounts_outside_the_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        from sqlalchemy import update

        from app.core.users.models import User
        from app.database.session import engine

        outsider = await register_user(client, prefix="outsider")
        async with engine.begin() as connection:
            await connection.execute(
                update(User).where(User.id == owner["user"]["id"]).values(is_superuser=True)
            )

        response = await _people(
            client, owner["token"], owner["organization"]["id"], scope="outside"
        )

        assert response.status_code == 200, response.text
        rows = response.json()["items"]
        usernames = {row["username"] for row in rows}
        assert outsider["user"]["username"] in usernames
        assert owner["user"]["username"] not in usernames
        # The column that tells the two kinds of row apart is not optional.
        assert all(row["in_organization"] is False for row in rows)
        assert all(row["role"] is None for row in rows)

    async def test_the_rows_carry_the_structure_the_table_sorts_by(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        colleague = await _join(client, owner, "colleague")
        headers = _headers(owner["token"])
        base = f"/api/v1/organizations/{owner['organization']['id']}"
        department = await client.post(
            f"{base}/departments",
            json={"name": "Support"},
            headers=headers,
        )
        position = await client.post(
            f"{base}/positions", json={"title": "Support lead"}, headers=headers
        )
        await client.patch(
            f"{base}/members/{colleague['user']['id']}/placement",
            json={"department_id": department.json()["id"], "position_id": position.json()["id"]},
            headers=headers,
        )

        response = await _people(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 200, response.text
        row = next(r for r in response.json()["items"] if r["id"] == colleague["user"]["id"])
        assert row["department_name"] == "Support"
        assert row["position_title"] == "Support lead"
        assert row["role"] == "member"

    async def test_sorting_and_filtering_are_the_servers_job(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A page sorted in the browser would order one page and contradict it
        on the next; the order has to come from the same query as the count."""
        for index in range(3):
            await _join(client, owner, f"person{index}")

        ascending = await _people(
            client, owner["token"], owner["organization"]["id"], sort="name", direction="asc"
        )
        names = [row["username"] for row in ascending.json()["items"]]
        assert names == sorted(names)

        descending = await _people(
            client, owner["token"], owner["organization"]["id"], sort="name", direction="desc"
        )
        assert [row["username"] for row in descending.json()["items"]] == sorted(
            names, reverse=True
        )

        filtered = await _people(
            client, owner["token"], owner["organization"]["id"], search="person1"
        )
        assert filtered.json()["total"] == 1
        assert len(filtered.json()["items"]) == 1

    async def test_sorting_by_role_goes_by_rank_not_by_spelling(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Alphabetically "admin" would come first and the owner last.

        A reader sorting by role is asking "who outranks whom", and the rank is
        the answer; the spelling is an accident of the alphabet.
        """
        await _join(client, owner, "viewer", role="viewer")
        await _join(client, owner, "member", role="member")
        await _join(client, owner, "admin", role="admin")

        ascending = await _people(
            client, owner["token"], owner["organization"]["id"], sort="role", direction="asc"
        )

        roles = [row["role"] for row in ascending.json()["items"] if row["role"]]
        assert roles[0] == "owner"
        assert roles.index("admin") < roles.index("member") < roles.index("viewer")

        descending = await _people(
            client, owner["token"], owner["organization"]["id"], sort="role", direction="desc"
        )
        reversed_roles = [row["role"] for row in descending.json()["items"] if row["role"]]
        assert reversed_roles[0] == "viewer"
        # Descending is the exact mirror: the viewer first, the owner last.
        assert reversed_roles.index("admin") < reversed_roles.index("owner")

    async def test_the_footer_count_matches_the_filter_that_was_applied(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Counted from the same statement, so a filter over a joined column
        (department, position) cannot make the count disagree with the rows."""
        for index in range(4):
            await _join(client, owner, f"person{index}")
        organization_id = owner["organization"]["id"]
        headers = _headers(owner["token"])
        department = await client.post(
            f"/api/v1/organizations/{organization_id}/departments",
            json={"name": "Support"},
            headers=headers,
        )

        everybody = await _people(client, owner["token"], organization_id, limit=2)
        assert everybody.json()["total"] == 5
        assert len(everybody.json()["items"]) == 2

        empty = await _people(
            client, owner["token"], organization_id, department_id=department.json()["id"]
        )
        assert empty.json()["total"] == 0
        assert empty.json()["items"] == []

    async def test_an_unknown_sort_key_is_refused_rather_than_guessed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The sort key becomes a column name in SQL; anything the screen does
        not offer is a 422, not something to interpolate."""
        response = await _people(
            client, owner["token"], owner["organization"]["id"], sort="password_hash"
        )

        assert response.status_code == 422
        assert "password_hash" in response.json()["error"]["message"]

    async def test_a_hidden_contact_is_not_handed_out_by_the_table(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The merged table is a new place to leak an address (stage 2.6).

        The person answered "administrators only", so the row exists, the name
        exists, and the address is null with the flag saying why.
        """
        person = await _join(client, owner, "shy")
        reader = await _join(client, owner, "reader")
        await client.put(
            f"/api/v1/users/me/settings?organization_id={owner['organization']['id']}",
            json={"values": {"contacts_visibility": "admins"}},
            headers=_headers(person["token"]),
        )

        as_reader = await _people(client, reader["token"], owner["organization"]["id"])
        row = next(r for r in as_reader.json()["items"] if r["id"] == person["user"]["id"])
        assert row["username"] == person["user"]["username"]
        assert row["email"] is None
        assert row["contacts_visible"] is False

        as_admin = await _people(client, owner["token"], owner["organization"]["id"])
        admin_row = next(r for r in as_admin.json()["items"] if r["id"] == person["user"]["id"])
        assert admin_row["email"] == person["user"]["email"]
        assert admin_row["contacts_visible"] is True


class TestAdminEditor:
    """One route for everything an administrator may change (stage 2.18)."""

    async def test_an_administrator_changes_name_address_and_birthday(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={
                "first_name": "Renamed",
                "last_name": "Person",
                "email": "renamed@example.com",
                "birthday": "1979-03-04",
            },
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["first_name"] == "Renamed"
        assert body["last_name"] == "Person"
        assert body["email"] == "renamed@example.com"
        assert body["birthday"] == "1979-03-04"

    async def test_a_birthday_can_be_removed_while_the_name_stays(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Absent means "leave it alone" and explicit null means "remove it", or
        a form that saves the name would erase the date."""
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]
        await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"birthday": "1979-03-04"},
            headers=_headers(owner["token"]),
        )

        untouched = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"last_name": "Kept"},
            headers=_headers(owner["token"]),
        )
        assert untouched.json()["birthday"] == "1979-03-04"

        cleared = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"birthday": None},
            headers=_headers(owner["token"]),
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["birthday"] is None

    async def test_the_role_and_the_placement_change_together(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]
        headers = _headers(owner["token"])
        department = await client.post(
            f"/api/v1/organizations/{organization_id}/departments",
            json={"name": "Support"},
            headers=headers,
        )
        position = await client.post(
            f"/api/v1/organizations/{organization_id}/positions",
            json={"title": "Support lead"},
            headers=headers,
        )

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={
                "role": "admin",
                "department_id": department.json()["id"],
                "position_id": position.json()["id"],
            },
            headers=headers,
        )

        assert response.status_code == 200, response.text
        row = (await _people(client, owner["token"], organization_id)).json()["items"]
        edited = next(r for r in row if r["id"] == person["user"]["id"])
        assert edited["role"] == "admin"
        assert edited["department_name"] == "Support"
        assert edited["position_title"] == "Support lead"

    async def test_a_refused_field_leaves_the_whole_person_untouched(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The reason this is one route and not four.

        A member may not change a role, so a form that also renames them must be
        refused whole: saving half of what was typed - a new name next to an
        old address - is how a UI starts lying about the state of the data.
        """
        person = await _join(client, owner, "person")
        colleague = await _join(client, owner, "colleague")
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"first_name": "Renamed", "role": "admin"},
            headers=_headers(colleague["token"]),
        )

        assert response.status_code == 403
        reread = await client.get(
            f"/api/v1/users/{person['user']['id']}/profile?organization_id={organization_id}",
            headers=_headers(owner["token"]),
        )
        assert reread.json()["first_name"] != "Renamed"
        row = next(
            r
            for r in (await _people(client, owner["token"], organization_id)).json()["items"]
            if r["id"] == person["user"]["id"]
        )
        assert row["role"] == "member"

    async def test_an_administrator_writes_somebody_elses_phone_numbers(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The whole set at once, because three calls leave half a list.

        The numbers travel masked or not and come back plain; the kind is the
        closed list, and a number the administrator leaves out of the list is
        removed rather than quietly kept.
        """
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]
        first = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "+7 900 000-00-01", "kind": "work"},
            headers=_headers(person["token"]),
        )
        assert first.status_code == 200, first.text

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={
                "phones": [
                    {"number": "+7 (900) 000-00-02", "kind": "mobile"},
                    {"number": "+7 900 000-00-03", "kind": "home"},
                ]
            },
            headers=_headers(owner["token"]),
        )
        assert response.status_code == 200, response.text

        left = (
            await client.get("/api/v1/users/me/phones", headers=_headers(person["token"]))
        ).json()
        assert [phone["number"] for phone in left] == ["+79000000002", "+79000000003"]
        assert [phone["kind"] for phone in left] == ["mobile", "home"]
        # The one the administrator dropped is gone, not left behind.
        assert first.json()["id"] not in {phone["id"] for phone in left}

    async def test_phones_are_untouched_unless_the_form_sends_them(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A form that saves a name must not quietly rewrite the phones.

        The keys left out are "leave it alone" for the same reason they are for
        the birthday: a list sent on every save would erase anything the person
        added in another tab.
        """
        person = await _join(client, owner, "person")
        await client.post(
            "/api/v1/users/me/phones",
            json={"number": "+7 900 000-00-01", "kind": "work"},
            headers=_headers(person["token"]),
        )

        await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={"last_name": "Changed"},
            headers=_headers(owner["token"]),
        )

        left = (
            await client.get("/api/v1/users/me/phones", headers=_headers(person["token"]))
        ).json()
        assert [phone["number"] for phone in left] == ["+79000000001"]

    async def test_an_ordinary_member_may_not_edit_anybody(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        colleague = await _join(client, owner, "colleague")

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={"first_name": "Renamed"},
            headers=_headers(colleague["token"]),
        )

        assert response.status_code == 403

    async def test_only_a_portal_administrator_may_lock_an_account(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A disabled login stops working in every organization the person
        belongs to, so the owner of one tenant may not do it."""
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]

        refused = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"status": "disabled"},
            headers=_headers(owner["token"]),
        )
        assert refused.status_code == 403
        assert "portal administrator" in refused.json()["error"]["message"]

        from sqlalchemy import update

        from app.core.users.models import User
        from app.database.session import engine

        async with engine.begin() as connection:
            await connection.execute(
                update(User).where(User.id == owner["user"]["id"]).values(is_superuser=True)
            )

        allowed = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={organization_id}",
            json={"status": "disabled"},
            headers=_headers(owner["token"]),
        )
        assert allowed.status_code == 200, allowed.text
        assert allowed.json()["status"] == "disabled"

        # And the lock actually holds: the person cannot sign in any more.
        login = await client.post(
            "/api/v1/auth/login",
            json={"login": person["user"]["email"], "password": "sup3r-secret"},
        )
        assert login.status_code == 401

    async def test_somebody_who_is_not_a_member_is_not_found(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        """Not "forbidden": the route is about a member of this organization, and
        an account that is not one cannot be edited through it."""
        response = await client.patch(
            f"/api/v1/users/{outsider['user']['id']}?organization_id={owner['organization']['id']}",
            json={"first_name": "Renamed"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 404

    async def test_an_empty_editor_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}?organization_id={owner['organization']['id']}",
            json={},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 422
        # Pydantic's own envelope rather than the domain one: a request that does
        # not even have a shape is FastAPI's to refuse, before any service runs.
        assert "at least one field" in response.text
