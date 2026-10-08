"""Organization settings: defaults, overrides and isolation."""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient

from app.core.settings.service import PERSONAL_SETTING_DEFINITIONS, SETTING_DEFINITIONS
from tests.conftest import auth_headers


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
