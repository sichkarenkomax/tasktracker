"""The shipped product shape: one organization, set up by an administrator.

The rest of the suite runs with ``SINGLE_ORGANIZATION`` and
``BOOTSTRAP_SUPERUSER`` off (see ``conftest.py``) so that the multi-tenant
surface keeps its coverage. These tests turn both flags back on and pin the
policy the product actually ships with:

* the first account registered on a fresh installation becomes the portal
  administrator, because every route that could grant the right requires it;
* that administrator sets the organization up, once;
* nobody - administrator included - can create a second one.
"""

from __future__ import annotations

from typing import Any

import pytest
from httpx import AsyncClient
from sqlalchemy import update

from app.config.settings import get_settings
from app.core.users.models import User
from app.database.session import engine
from tests.conftest import auth_headers, create_organization, register_user


@pytest.fixture
def product_shape(monkeypatch: pytest.MonkeyPatch) -> None:
    """Switch the cached settings singleton to the shipped defaults."""
    settings = get_settings()
    monkeypatch.setattr(settings, "single_organization", True)
    monkeypatch.setattr(settings, "bootstrap_superuser", True)


async def _profile(client: AsyncClient, token: str) -> dict[str, Any]:
    response = await client.get("/api/v1/users/me", headers=auth_headers(token))
    assert response.status_code == 200, response.text
    return response.json()


class TestBootstrapAdministrator:
    async def test_the_first_account_is_the_administrator(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")

        assert (await _profile(client, first["access_token"]))["is_superuser"] is True

    async def test_every_later_account_is_ordinary(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        await register_user(client, prefix="first")
        second = await register_user(client, prefix="second")

        assert (await _profile(client, second["access_token"]))["is_superuser"] is False


class TestSingleOrganization:
    async def test_a_plain_account_cannot_set_the_organization_up(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")
        second = await register_user(client, prefix="second")

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Acme"},
            headers=auth_headers(second["access_token"]),
        )

        # The first account has not created one yet, so this is the
        # permission guard rather than the one-organization guard speaking.
        assert response.status_code == 403, response.text
        assert (await _profile(client, first["access_token"]))["is_superuser"] is True

    async def test_the_administrator_creates_the_organization(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")

        response = await client.post(
            "/api/v1/organizations",
            json={"name": "Acme"},
            headers=auth_headers(first["access_token"]),
        )

        assert response.status_code == 201, response.text

    async def test_a_second_organization_is_refused(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")
        await create_organization(client, first["access_token"])
        second = await register_user(client, prefix="second")

        as_administrator = await client.post(
            "/api/v1/organizations",
            json={"name": "Another"},
            headers=auth_headers(first["access_token"]),
        )
        as_plain_account = await client.post(
            "/api/v1/organizations",
            json={"name": "Another"},
            headers=auth_headers(second["access_token"]),
        )

        assert as_administrator.status_code == 409, as_administrator.text
        # Permission is checked before existence, so a refusal never discloses
        # whether the single organization is already there.
        assert as_plain_account.status_code == 403, as_plain_account.text


class TestAdministratorVisibility:
    async def test_an_administrator_sees_an_organization_they_have_not_joined(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")
        await create_organization(client, first["access_token"])
        helper = await register_user(client, prefix="helper")

        # The way an installation would grant it: no API allows self-service.
        async with engine.begin() as connection:
            await connection.execute(
                update(User).where(User.id == str(helper["user"]["id"])).values(is_superuser=True)
            )

        response = await client.get(
            "/api/v1/organizations", headers=auth_headers(helper["access_token"])
        )

        assert response.status_code == 200, response.text
        assert [organization["name"] for organization in response.json()] == ["Acme"]

    async def test_a_plain_account_still_sees_only_their_own(
        self, client: AsyncClient, product_shape: None
    ) -> None:
        first = await register_user(client, prefix="first")
        await create_organization(client, first["access_token"])
        second = await register_user(client, prefix="second")

        response = await client.get(
            "/api/v1/organizations", headers=auth_headers(second["access_token"])
        )

        assert response.status_code == 200
        assert response.json() == []
