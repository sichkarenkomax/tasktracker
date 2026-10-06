"""The portal administrator.

`is_superuser` is the one permission in the product that is not scoped to an
organization: it crosses tenants. It therefore lives on a column with its own
guard rather than among the four organization roles, and these tests pin both
halves of that decision - who is refused, and what an administrator can then see
that nobody else can.
"""

from __future__ import annotations

from typing import Any

from httpx import AsyncClient
from sqlalchemy import update

from app.core.users.models import User
from app.database.session import engine
from tests.conftest import auth_headers, register_user


async def _make_admin(user_id: str) -> None:
    """Grant the right the way an installation would: in the database.

    The API deliberately offers no way to bootstrap the first administrator -
    every route that can set the flag requires it already. A fresh install gets
    its first one from the environment or the database, so the test does the same.
    """
    async with engine.begin() as connection:
        await connection.execute(update(User).where(User.id == user_id).values(is_superuser=True))


class TestUserDirectory:
    async def test_a_plain_account_is_refused(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        response = await client.get("/api/v1/users", headers=auth_headers(owner["token"]))

        assert response.status_code == 403

    async def test_an_administrator_lists_every_account(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])
        stranger = await register_user(client, prefix="stranger")

        response = await client.get(
            "/api/v1/users", params={"limit": 100}, headers=auth_headers(owner["token"])
        )

        assert response.status_code == 200
        body = response.json()
        emails = {item["email"] for item in body["items"]}
        assert owner["user"]["email"] in emails
        assert stranger["user"]["email"] in emails
        assert body["total"] >= 2

    async def test_the_search_narrows_the_list(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])
        handle = owner["user"]["username"]

        response = await client.get(
            "/api/v1/users",
            params={"search": handle, "limit": 100},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        assert body["items"][0]["username"] == handle

    async def test_a_search_that_matches_nothing_is_empty_not_an_error(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])

        response = await client.get(
            "/api/v1/users",
            params={"search": "nobody-by-that-name"},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["items"] == []


class TestGranting:
    async def test_an_administrator_grants_the_right(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])
        target = await register_user(client, prefix="promoted")

        response = await client.patch(
            f"/api/v1/users/{target['user']['id']}/superuser",
            json={"is_superuser": True},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200, response.text
        assert response.json()["is_superuser"] is True

        # And the promotion actually opens the directory for them.
        listed = await client.get("/api/v1/users", headers=auth_headers(target["access_token"]))
        assert listed.status_code == 200

    async def test_the_right_is_revoked_again(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])
        target = await register_user(client, prefix="promoted")
        await client.patch(
            f"/api/v1/users/{target['user']['id']}/superuser",
            json={"is_superuser": True},
            headers=auth_headers(owner["token"]),
        )

        response = await client.patch(
            f"/api/v1/users/{target['user']['id']}/superuser",
            json={"is_superuser": False},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
        assert response.json()["is_superuser"] is False
        refused = await client.get("/api/v1/users", headers=auth_headers(target["access_token"]))
        assert refused.status_code == 403

    async def test_nobody_can_grant_the_right_without_it(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Including an organization owner: admin of one tenant is not admin of
        the installation, and conflating the two would be a privilege escalation."""
        response = await client.patch(
            f"/api/v1/users/{owner['user']['id']}/superuser",
            json={"is_superuser": True},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 403

    async def test_an_administrator_cannot_demote_themselves(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """Otherwise the last administrator can lock everybody - and the fix -
        out of the only screen that grants it."""
        await _make_admin(owner["user"]["id"])

        response = await client.patch(
            f"/api/v1/users/{owner['user']['id']}/superuser",
            json={"is_superuser": False},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 403

    async def test_an_unknown_account_is_404(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        await _make_admin(owner["user"]["id"])

        response = await client.patch(
            "/api/v1/users/00000000-0000-0000-0000-000000000000/superuser",
            json={"is_superuser": True},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 404

    async def test_the_right_needs_no_organization(
        self, client: AsyncClient, owner: dict[str, Any]
    ) -> None:
        """It is not an organization grant, so the route must not ask for one."""
        await _make_admin(owner["user"]["id"])
        target = await register_user(client, prefix="promoted")

        response = await client.patch(
            f"/api/v1/users/{target['user']['id']}/superuser",
            json={"is_superuser": True},
            headers=auth_headers(owner["token"]),
        )

        assert response.status_code == 200
