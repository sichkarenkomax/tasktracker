"""Organization settings: defaults, overrides and isolation."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.core.settings.service import PERSONAL_SETTING_DEFINITIONS, SETTING_DEFINITIONS
from tests.conftest import auth_headers, register_user


def settings_url(organization_id: str) -> str:
    return f"/api/v1/organizations/{organization_id}/settings"


async def read_settings(client: AsyncClient, token: str, organization_id: str) -> Any:
    return await client.get(settings_url(organization_id), headers=auth_headers(token))


async def write_settings(
    client: AsyncClient, token: str, organization_id: str, values: dict[str, Any]
) -> Any:
    return await client.put(
        settings_url(organization_id),
        json={"values": values},
        headers=auth_headers(token),
    )


class TestDefaults:
    async def test_every_known_setting_is_present_before_any_write(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await read_settings(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 200
        body = response.json()
        assert set(body["values"]) == set(SETTING_DEFINITIONS)
        assert body["values"]["locale"] == "en"
        assert body["values"]["timezone"] == "UTC"

    async def test_definitions_describe_type_and_default(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        body = (await read_settings(client, owner["token"], owner["organization"]["id"])).json()

        assert body["available"]["week_starts_on"] == {"type": "integer", "default": 1}

    async def test_a_member_may_read_settings(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": outsider["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )

        response = await read_settings(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 200

    async def test_a_non_member_may_not_read_settings(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        response = await read_settings(client, outsider["token"], owner["organization"]["id"])

        assert response.status_code == 403


class TestWrite:
    async def test_override_replaces_the_default(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]

        written = await write_settings(
            client, owner["token"], organization_id, {"locale": "de", "timezone": "Europe/Berlin"}
        )
        reread = await read_settings(client, owner["token"], organization_id)

        assert written.json()["values"]["locale"] == "de"
        assert reread.json()["values"]["locale"] == "de"
        assert reread.json()["values"]["timezone"] == "Europe/Berlin"
        # Untouched keys keep their default.
        assert reread.json()["values"]["date_format"] == "YYYY-MM-DD"

    async def test_overwriting_is_an_update_not_a_duplicate(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]
        await write_settings(client, owner["token"], organization_id, {"locale": "de"})
        await write_settings(client, owner["token"], organization_id, {"locale": "fr"})

        body = (await read_settings(client, owner["token"], organization_id)).json()

        assert body["values"]["locale"] == "fr"

    async def test_unknown_key_is_rejected_and_lists_the_available_ones(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await write_settings(
            client, owner["token"], owner["organization"]["id"], {"nonsense": 1}
        )

        assert response.status_code == 404
        assert "nonsense" in response.json()["error"]["message"]
        assert "locale" in response.json()["error"]["details"]["available"]

    async def test_a_value_the_key_does_not_accept_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The portal's date format is rendered by the browser, so a value it
        cannot draw is refused here instead of being stored and quietly ignored.

        Keys no frontend renders stay free-form - a module validates its own.
        """
        response = await write_settings(
            client, owner["token"], owner["organization"]["id"], {"date_format": "next tuesday"}
        )

        assert response.status_code == 422
        assert "next tuesday" in response.json()["error"]["message"]

        reread = (await read_settings(client, owner["token"], owner["organization"]["id"])).json()
        assert reread["values"]["date_format"] == SETTING_DEFINITIONS["date_format"]["default"]

    async def test_a_plain_member_may_not_write(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": outsider["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )

        response = await write_settings(
            client, outsider["token"], owner["organization"]["id"], {"locale": "de"}
        )

        assert response.status_code == 403


class TestIsolation:
    async def test_overrides_do_not_leak_between_organizations(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        from tests.conftest import create_organization, register_user

        session = await register_user(client, prefix="other")
        other_token = session["access_token"]
        other = await create_organization(client, other_token)

        await write_settings(client, owner["token"], owner["organization"]["id"], {"locale": "de"})

        theirs = (await read_settings(client, other_token, other["id"])).json()

        assert theirs["values"]["locale"] == "en"


def personal_url(organization_id: str) -> str:
    return f"/api/v1/users/me/settings?organization_id={organization_id}"


async def read_personal(client: AsyncClient, token: str, organization_id: str) -> Any:
    return await client.get(personal_url(organization_id), headers=auth_headers(token))


async def write_personal(
    client: AsyncClient, token: str, organization_id: str, values: dict[str, Any]
) -> Any:
    return await client.put(
        personal_url(organization_id),
        json={"values": values},
        headers=auth_headers(token),
    )


class TestPersonalSettings:
    """The preferences screen's storage: per person, per organization."""

    async def test_every_declared_key_is_present_before_any_write(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await read_personal(client, owner["token"], owner["organization"]["id"])

        assert response.status_code == 200
        body = response.json()
        assert set(body["values"]) == set(PERSONAL_SETTING_DEFINITIONS)
        assert body["values"]["theme"] == "gold"

    async def test_a_member_writes_their_own_without_any_permission(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The one write these settings always allow: a person deciding their own.

        Organization settings need `organization.settings.manage`; a theme does
        not, and requiring a permission to pick a colour would be the wrong rule.
        """
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": owner["user"]["email"], "role": "owner"},
            headers=auth_headers(owner["token"]),
        )

        response = await write_personal(
            client, owner["token"], owner["organization"]["id"], {"theme": "blue"}
        )

        assert response.status_code == 200, response.text
        assert response.json()["values"]["theme"] == "blue"

        reread = await read_personal(client, owner["token"], owner["organization"]["id"])
        assert reread.json()["values"]["theme"] == "blue"

    async def test_an_outsider_may_not_read_or_write(
        self, client: AsyncClient, owner: dict[str, Any], outsider: dict[str, Any]
    ) -> None:
        organization_id = owner["organization"]["id"]

        assert (await read_personal(client, outsider["token"], organization_id)).status_code == 403
        assert (
            await write_personal(client, outsider["token"], organization_id, {"theme": "blue"})
        ).status_code == 403

    async def test_two_members_keep_separate_settings(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """A setting is a person's, not a property of the office they sit in."""
        await client.post(
            f"/api/v1/organizations/{owner['organization']['id']}/members",
            json={"email": owner["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )
        organization_id = owner["organization"]["id"]

        await write_personal(client, owner["token"], organization_id, {"theme": "blue"})

        theirs = (await read_personal(client, owner["token"], organization_id)).json()
        assert theirs["values"]["theme"] == "blue"

    async def test_unknown_key_is_refused(self, client: AsyncClient, owner: dict[str, Any]) -> None:
        response = await write_personal(
            client, owner["token"], owner["organization"]["id"], {"font": "comic"}
        )

        assert response.status_code == 404
        assert "font" in response.json()["error"]["message"]
        assert "theme" in response.json()["error"]["details"]["available"]

    async def test_stored_says_what_was_chosen_and_does_not_merge_defaults(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The difference between "they picked this" and "nobody picked anything".

        `values` carries every key with its default, so a client that read it as
        an opinion would pin everybody to the default and leave the portal's own
        date format unreachable. `stored` stays empty until something is written.
        """
        organization_id = owner["organization"]["id"]

        before = (await read_personal(client, owner["token"], organization_id)).json()
        assert before["stored"] == {}
        assert (
            before["values"]["date_format"]
            == PERSONAL_SETTING_DEFINITIONS["date_format"]["default"]
        )

        await write_personal(client, owner["token"], organization_id, {"date_format": "DD.MM.YY"})

        after = (await read_personal(client, owner["token"], organization_id)).json()
        assert after["stored"] == {"date_format": "DD.MM.YY"}
        assert after["values"]["date_format"] == "DD.MM.YY"
        assert "theme" not in after["stored"]

    async def test_a_personal_value_the_key_does_not_accept_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await write_personal(
            client, owner["token"], owner["organization"]["id"], {"date_format": "next tuesday"}
        )

        assert response.status_code == 422
        assert "next tuesday" in response.json()["error"]["message"]

        reread = (await read_personal(client, owner["token"], owner["organization"]["id"])).json()
        assert (
            reread["values"]["date_format"]
            == PERSONAL_SETTING_DEFINITIONS["date_format"]["default"]
        )

    async def test_how_much_of_a_person_is_shown_is_personal(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """The pickers' amount of detail (stage 2.5), and nobody else's business.

        It is a personal key with no portal-side twin: one person reads every
        roster with positions under the names, a colleague in the same portal
        reads names only, and neither of them is mistaken about why.
        """
        organization_id = owner["organization"]["id"]

        defaults = (await read_personal(client, owner["token"], organization_id)).json()
        assert defaults["values"]["people_info"] == "full"
        assert defaults["stored"] == {}

        await write_personal(client, owner["token"], organization_id, {"people_info": "names"})

        chosen = (await read_personal(client, owner["token"], organization_id)).json()
        assert chosen["stored"] == {"people_info": "names"}
        assert chosen["values"]["people_info"] == "names"

        # The colleague's answer is unchanged, which is the whole point of it
        # being personal rather than an organization setting.
        colleague = await register_user(client, prefix="colleague")
        await client.post(
            f"/api/v1/organizations/{organization_id}/members",
            json={"email": colleague["user"]["email"], "role": "member"},
            headers=auth_headers(owner["token"]),
        )

        other = await write_personal(
            client, colleague["access_token"], organization_id, {"people_info": "full"}
        )
        assert other.status_code == 200
        assert (await read_personal(client, colleague["access_token"], organization_id)).json()[
            "stored"
        ] == {"people_info": "full"}
        assert (await read_personal(client, owner["token"], organization_id)).json()["stored"] == {
            "people_info": "names"
        }

    async def test_an_unknown_amount_of_detail_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Only the two values the frontend reads may be stored.

        A third spelling would be accepted by a free-form key and then read as
        "not full", quietly showing names only to the person who asked for
        something else.
        """
        response = await write_personal(
            client, owner["token"], owner["organization"]["id"], {"people_info": "everything"}
        )

        assert response.status_code == 422
        assert "everything" in response.json()["error"]["message"]

        reread = (await read_personal(client, owner["token"], owner["organization"]["id"])).json()
        assert reread["stored"] == {}
        assert (
            reread["values"]["people_info"]
            == PERSONAL_SETTING_DEFINITIONS["people_info"]["default"]
        )
