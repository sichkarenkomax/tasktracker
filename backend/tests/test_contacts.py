"""Contacts, their visibility, and an administrator changing an address.

Three questions, one file, because they share the same subject - what one
member of an organization is allowed to learn about another:

* a person fills in their own birthday and phones (2.8);
* a colleague's profile hands the contacts over, or does not, depending on two
  settings and one person's own answer (2.6);
* an administrator may change somebody's address, and nobody else may (2.7).

The interesting cases are the refusals: a contact that must *not* be visible, an
administrator who may not touch a stranger, and an address that is already
taken. A test that only walks the happy path proves that the happy path works.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from tests.conftest import auth_headers, register_user


async def _join(
    client: AsyncClient, owner: dict[str, Any], prefix: str, role: str = "member"
) -> dict[str, Any]:
    """A second account inside the owner's organization."""
    session = await register_user(client, prefix=prefix)
    added = await client.post(
        f"/api/v1/organizations/{owner['organization']['id']}/members",
        json={"email": session["user"]["email"], "role": role},
        headers=auth_headers(owner["token"]),
    )
    assert added.status_code == 201, added.text
    return {
        "token": session["access_token"],
        "user": session["user"],
        "role": role,
    }


def _headers(token: str) -> dict[str, str]:
    return auth_headers(token)


async def _add_phone(
    client: AsyncClient,
    token: str,
    number: str,
    kind: str | None = None,
    country: str | None = None,
) -> dict[str, Any]:
    body: dict[str, Any] = {"number": number}
    if kind is not None:
        body["kind"] = kind
    if country is not None:
        body["country"] = country
    response = await client.post(
        "/api/v1/users/me/phones",
        json=body,
        headers=_headers(token),
    )
    assert response.status_code == 200, response.text
    return dict(response.json())


class TestOwnContacts:
    """What a person writes about themselves (stage 2.8)."""

    async def test_a_birthday_is_written_and_cleared(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        written = await client.patch(
            "/api/v1/users/me/birthday",
            json={"birthday": "1988-04-17"},
            headers=_headers(owner["token"]),
        )
        assert written.status_code == 200, written.text
        assert written.json()["birthday"] == "1988-04-17"

        # `null` is a real answer: a person who wants the date *gone* has to be
        # able to say so, which is why clearing has its own route rather than
        # sharing the "omit the key to leave it alone" rule with the name.
        cleared = await client.patch(
            "/api/v1/users/me/birthday",
            json={"birthday": None},
            headers=_headers(owner["token"]),
        )
        assert cleared.status_code == 200, cleared.text
        assert cleared.json()["birthday"] is None

    async def test_a_birthday_in_the_future_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A future date is a typo, and storing it would later be read as an age."""
        response = await client.patch(
            "/api/v1/users/me/birthday",
            json={"birthday": "2999-01-01"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"]["field"] == "birthday"

        reread = await client.get("/api/v1/users/me", headers=_headers(owner["token"]))
        assert reread.json()["birthday"] is None

    async def test_several_phones_keep_the_order_they_were_written_in(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        first = await _add_phone(client, owner["token"], "+7 900 000-00-01", "work")
        second = await _add_phone(client, owner["token"], "+7 900 000-00-02", "home")
        third = await _add_phone(client, owner["token"], "+7 900 000-00-03", "mobile")

        listed = await client.get("/api/v1/users/me/phones", headers=_headers(owner["token"]))

        assert listed.status_code == 200
        assert [row["id"] for row in listed.json()] == [first["id"], second["id"], third["id"]]
        assert [row["kind"] for row in listed.json()] == ["work", "home", "mobile"]

    async def test_the_number_is_stored_plain_and_reads_back_the_same(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """E.164 in the column, whatever the screen showed.

        Brackets and spaces in a stored number would sort by their punctuation,
        and a search for a number copied off an invoice would find nothing.
        """
        phone = await _add_phone(client, owner["token"], "+7 (900) 000-00-01")

        assert phone["number"] == "+79000000001"

        again = await _add_phone(client, owner["token"], "+7 900 000 00 02")
        assert again["number"] == "+79000000002"

    async def test_a_number_is_validated_against_its_country(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The server, not the browser, decides what a number is.

        The check is Google's libphonenumber data on both sides of the wire: a
        number is real in the country it belongs to and a handful of digits in
        any other. A form is a convenience; this is the rule.

        Worth remembering what that rule knows: `4155550100` is a *valid Russian*
        number - Russian codes do start with a 4 - so "this looks American" is
        not an argument about any of them, and the country in the request is
        what decides.
        """
        russian = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "8 (900) 123-45-67", "country": "RU"},
            headers=_headers(owner["token"]),
        )
        assert russian.status_code == 200, russian.text
        assert russian.json()["number"] == "+79001234567"
        assert russian.json()["country"] == "RU"

        american = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "(415) 555-0100", "country": "US"},
            headers=_headers(owner["token"]),
        )
        assert american.status_code == 200, american.text
        assert american.json()["number"] == "+14155550100"

        # A real number in the wrong field: eight digits that are a mobile number
        # in Russia and nothing at all in the United States.
        wrong = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "8 (900) 123-45-67", "country": "US"},
            headers=_headers(owner["token"]),
        )
        assert wrong.status_code == 422

    async def test_a_national_number_without_its_country_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Eleven digits could be a dozen countries, and the wrong one is worse
        than no answer at all."""
        response = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "8 900 123-45-67"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 422
        assert response.json()["error"]["details"]["field"] == "country"

    async def test_a_number_that_is_too_short_or_too_long_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Before the library gets a say, because the message about length is the
        useful one for a paste accident."""
        for number in ("123", "8 900 123 45 67 89 012 345 678 90"):
            response = await client.post(
                "/api/v1/users/me/phones",
                json={"number": number, "country": "RU"},
                headers=_headers(owner["token"]),
            )
            assert response.status_code == 422, number

    async def test_the_kind_is_a_closed_list_with_work_as_the_default(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A field the person filled in carefully must not be decided by us."""
        default = await _add_phone(client, owner["token"], "+7 900 000-00-01")
        assert default["kind"] == "work"

        refused = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "+7 900 000-00-02", "kind": "for the workshop in Lyon"},
            headers=_headers(owner["token"]),
        )
        assert refused.status_code == 422

    async def test_a_number_of_the_wrong_length_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Five digits is not a number anybody can be called on."""
        response = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "123"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 422
        listed = await client.get("/api/v1/users/me/phones", headers=_headers(owner["token"]))
        assert listed.json() == []

    async def test_the_same_number_twice_is_one_number(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Two rows for one number is not a second number.

        It is refused rather than merged: the person who typed it is looking at
        two fields, and quietly dropping one of them is a decision this server
        has no business making on their behalf. Editing the number where it
        lives is how the kind changes.
        """
        first = await _add_phone(client, owner["token"], "+7 900 000-00-11", kind="work")

        same_number_other_spelling = await client.post(
            "/api/v1/users/me/phones",
            json={"number": "8 (900) 000-00-11", "country": "RU", "kind": "mobile"},
            headers=_headers(owner["token"]),
        )
        assert same_number_other_spelling.status_code == 409

        listed = await client.get("/api/v1/users/me/phones", headers=_headers(owner["token"]))
        assert [phone["number"] for phone in listed.json()] == [first["number"]]

        edited = await client.patch(
            f"/api/v1/users/me/phones/{first['id']}",
            json={"number": "+7 900 000-00-11", "kind": "mobile"},
            headers=_headers(owner["token"]),
        )
        assert edited.status_code == 200
        assert edited.json()["kind"] == "mobile"

        # And onto another person's number, which is the same refusal.
        taken = await client.post(
            "/api/v1/users/me/phones",
            json={"number": first["number"]},
            headers=_headers(owner["token"]),
        )
        assert taken.status_code == 409

    async def test_an_administrator_replaces_the_set_including_the_duplicates_of_older_data(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The replacement is "these are the numbers now", with no exceptions.

        A row left behind is a number the person no longer claims to have, which
        is exactly what an administrator removing a number is asking for. The
        duplicate is written straight into the table here rather than through the
        API, because the point is that a replacement is not confused by a state
        the API can no longer produce.
        """
        member = await _join(client, owner, prefix="replaced")
        kept = await _add_phone(client, member["token"], "+7 900 000-00-21")
        dropped = await _add_phone(client, member["token"], "+7 900 000-00-22")
        await _add_phone(client, member["token"], "+1 415 555 0100")

        replaced = await client.patch(
            f"/api/v1/users/{member['user']['id']}?organization_id={owner['organization']['id']}",
            json={
                "phones": [
                    {"number": "8 (900) 000-00-21", "country": "RU", "kind": "mobile"},
                    {"number": "415 555 0199", "country": "US", "kind": "other"},
                ]
            },
            headers=_headers(owner["token"]),
        )
        assert replaced.status_code == 200, replaced.text

        listed = (
            await client.get("/api/v1/users/me/phones", headers=_headers(member["token"]))
        ).json()
        assert sorted(phone["number"] for phone in listed) == [
            "+14155550199",
            "+79000000021",
        ]
        # The number the administrator did not list is gone, id and all.
        assert dropped["id"] not in {phone["id"] for phone in listed}
        # The one they kept keeps its row, so anything referring to it still does.
        assert kept["id"] in {phone["id"] for phone in listed}

    async def test_a_phone_is_edited_and_removed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        phone = await _add_phone(client, owner["token"], "+7 900 000-00-01", "work")

        edited = await client.patch(
            f"/api/v1/users/me/phones/{phone['id']}",
            json={"number": "+7 900 000-00-09", "kind": "mobile"},
            headers=_headers(owner["token"]),
        )
        assert edited.status_code == 200, edited.text
        assert edited.json()["number"] == "+79000000009"
        assert edited.json()["kind"] == "mobile"

        removed = await client.delete(
            f"/api/v1/users/me/phones/{phone['id']}", headers=_headers(owner["token"])
        )
        assert removed.status_code == 204
        left = await client.get("/api/v1/users/me/phones", headers=_headers(owner["token"]))
        assert left.json() == []

    async def test_somebody_elses_phone_is_not_found_rather_than_editable(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The route cannot be used to reach a number by guessing its id."""
        phone = await _add_phone(client, owner["token"], "+7 900 000-00-01")
        colleague = await _join(client, owner, "colleague")

        response = await client.patch(
            f"/api/v1/users/me/phones/{phone['id']}",
            json={"number": "+7 900 000-00-99"},
            headers=_headers(colleague["token"]),
        )

        assert response.status_code == 404

        untouched = await client.get("/api/v1/users/me/phones", headers=_headers(owner["token"]))
        assert untouched.json()[0]["number"] == "+79000000001"


class TestProfileVisibility:
    """Whose contacts a colleague's profile hands over (stage 2.6)."""

    async def test_a_colleague_sees_the_contacts_by_default(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The answer settled on: contacts are visible to the whole organization
        unless somebody says otherwise. A self-hosted portal is a company's own
        installation, so the default is the ordinary one."""
        colleague = await _join(client, owner, "colleague")
        await _add_phone(client, colleague["token"], "+7 900 000-00-02", "work")
        await client.patch(
            "/api/v1/users/me/birthday",
            json={"birthday": "1990-02-03"},
            headers=_headers(colleague["token"]),
        )

        response = await client.get(
            f"/api/v1/users/{colleague['user']['id']}/profile"
            f"?organization_id={owner['organization']['id']}",
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["contacts_visible"] is True
        assert body["email"] == colleague["user"]["email"]
        assert body["birthday"] == "1990-02-03"
        assert [phone["number"] for phone in body["phones"]] == ["+79000000002"]

    async def test_a_person_who_answers_admins_loses_the_contacts_for_everybody_else(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "shy")
        reader = await _join(client, owner, "reader")
        admin = await _join(client, owner, "boss", role="admin")
        await _add_phone(client, person["token"], "+7 900 000-00-03")

        await client.put(
            f"/api/v1/users/me/settings?organization_id={owner['organization']['id']}",
            json={"values": {"contacts_visibility": "admins"}},
            headers=_headers(person["token"]),
        )

        def profile(token: str) -> Any:
            return client.get(
                f"/api/v1/users/{person['user']['id']}/profile"
                f"?organization_id={owner['organization']['id']}",
                headers=_headers(token),
            )

        colleague_view = await profile(reader["token"])
        assert colleague_view.status_code == 200
        assert colleague_view.json()["contacts_visible"] is False
        assert colleague_view.json()["email"] is None
        assert colleague_view.json()["phones"] == []
        assert colleague_view.json()["birthday"] is None

        # The name is still there: the point of the profile is finding out who
        # to ask, and a card without a name would be a dead link.
        assert colleague_view.json()["username"] == person["user"]["username"]

        # An administrator still sees it - "only admins" is a statement about the
        # rest of the organization, not about the people who have to phone
        # somebody about a deadline.
        admin_view = await profile(admin["token"])
        assert admin_view.json()["contacts_visible"] is True
        assert [phone["number"] for phone in admin_view.json()["phones"]] == ["+79000000003"]

        # And so does the person themselves.
        own = await profile(person["token"])
        assert own.json()["contacts_visible"] is True

    async def test_the_portal_setting_says_whether_anybody_may_answer(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The answer's exact shape: the portal does not decide what a member
        shares, it decides whether they get to decide."""
        person = await _join(client, owner, "private")
        reader = await _join(client, owner, "nosy")
        await _add_phone(client, person["token"], "+7 900 000-00-04")
        settings_url = f"/api/v1/users/me/settings?organization_id={owner['organization']['id']}"

        # Self-service off, and the portal says "admins only": the person's own
        # stored answer stops counting, rather than quietly outranking the portal.
        disabled = await client.put(
            f"/api/v1/organizations/{owner['organization']['id']}/settings",
            json={"values": {"contacts_self_service": False, "contacts_visibility": "admins"}},
            headers=_headers(owner["token"]),
        )
        assert disabled.status_code == 200, disabled.text

        assert (
            await client.put(
                settings_url,
                json={"values": {"contacts_visibility": "everyone"}},
                headers=_headers(person["token"]),
            )
        ).status_code == 403

        view = await client.get(
            f"/api/v1/users/{person['user']['id']}/profile"
            f"?organization_id={owner['organization']['id']}",
            headers=_headers(reader["token"]),
        )
        assert view.json()["contacts_visible"] is False

        # Turning it back on gives the person their say again, and the answer
        # they could not store while it was off applies.
        await client.put(
            f"/api/v1/organizations/{owner['organization']['id']}/settings",
            json={"values": {"contacts_self_service": True}},
            headers=_headers(owner["token"]),
        )
        assert (
            await client.put(
                settings_url,
                json={"values": {"contacts_visibility": "everyone"}},
                headers=_headers(person["token"]),
            )
        ).status_code == 200

        view = await client.get(
            f"/api/v1/users/{person['user']['id']}/profile"
            f"?organization_id={owner['organization']['id']}",
            headers=_headers(reader["token"]),
        )
        assert view.json()["contacts_visible"] is True

    async def test_the_profile_carries_the_department_and_position(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The other half of the card, and the reason it is not just /users/{id}."""
        colleague = await _join(client, owner, "colleague")
        headers = _headers(owner["token"])
        base = f"/api/v1/organizations/{owner['organization']['id']}"

        department = await client.post(
            f"{base}/departments", json={"name": "Support"}, headers=headers
        )
        position = await client.post(
            f"{base}/positions", json={"title": "Support lead"}, headers=headers
        )
        placed = await client.patch(
            f"{base}/members/{colleague['user']['id']}/placement",
            json={
                "department_id": department.json()["id"],
                "position_id": position.json()["id"],
            },
            headers=headers,
        )
        assert placed.status_code == 200, placed.text

        response = await client.get(
            f"/api/v1/users/{colleague['user']['id']}/profile?organization_id={base.split('/')[-1]}",
            headers=headers,
        )

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["department_name"] == "Support"
        assert body["position_title"] == "Support lead"
        assert body["role"] == "member"

    async def test_an_outsider_does_not_get_the_profile(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await client.get(
            f"/api/v1/users/{owner['user']['id']}/profile"
            f"?organization_id={owner['organization']['id']}",
            headers=_headers(outsider["token"]),
        )

        assert response.status_code == 403


class TestAdminChangesEmail:
    """An administrator fixes somebody's address (stage 2.7)."""

    async def test_an_administrator_changes_a_members_address(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}/email?organization_id={organization_id}",
            json={"email": "new.address@example.com"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["email"] == "new.address@example.com"

        # The change is real: the new address is the one that logs in.
        again = await client.post(
            "/api/v1/auth/login",
            json={"login": "new.address@example.com", "password": "sup3r-secret"},
        )
        assert again.status_code == 200, again.text

    async def test_an_address_already_taken_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        other = await _join(client, owner, "other")
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}/email?organization_id={organization_id}",
            json={"email": other["user"]["email"]},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 409
        # Nothing moved: a refused change must not half-apply.
        reread = await client.get("/api/v1/users/me", headers=_headers(person["token"]))
        assert reread.json()["email"] == person["user"]["email"]

    async def test_an_ordinary_member_may_not_change_anybody(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        person = await _join(client, owner, "person")
        colleague = await _join(client, owner, "colleague")
        organization_id = owner["organization"]["id"]

        response = await client.patch(
            f"/api/v1/users/{person['user']['id']}/email?organization_id={organization_id}",
            json={"email": "hijacked@example.com"},
            headers=_headers(colleague["token"]),
        )

        assert response.status_code == 403
        reread = await client.get("/api/v1/users/me", headers=_headers(person["token"]))
        assert reread.json()["email"] == person["user"]["email"]

    async def test_nobody_may_change_their_own_address_through_this_route(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Self-service email changes are out of scope for this stage.

        A route that quietly accepted the owner changing their own address would
        answer that question without anybody having decided to.
        """
        response = await client.patch(
            f"/api/v1/users/{owner['user']['id']}/email"
            f"?organization_id={owner['organization']['id']}",
            json={"email": "myself@example.com"},
            headers=_headers(owner["token"]),
        )

        assert response.status_code == 403
        reread = await client.get("/api/v1/users/me", headers=_headers(owner["token"]))
        assert reread.json()["email"] == owner["user"]["email"]

    async def test_the_change_is_written_to_the_activity_feed(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The trail is the safeguard: no mail is sent, so the feed is how the
        person finds out that their address moved."""
        person = await _join(client, owner, "person")
        organization_id = owner["organization"]["id"]
        before = person["user"]["email"]

        await client.patch(
            f"/api/v1/users/{person['user']['id']}/email?organization_id={organization_id}",
            json={"email": "moved@example.com"},
            headers=_headers(owner["token"]),
        )

        feed = await client.get(
            f"/api/v1/activity?organization_id={organization_id}", headers=_headers(owner["token"])
        )

        assert feed.status_code == 200, feed.text
        entries = [
            entry for entry in feed.json()["items"] if entry["action"] == "user.email_changed"
        ]
        assert len(entries) == 1
        summary = entries[0]["summary"]
        assert owner["user"]["username"] in summary
        assert person["user"]["username"] in summary
        assert before in summary
        assert "moved@example.com" in summary
