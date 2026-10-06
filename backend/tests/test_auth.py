"""Registration, login, session and password change.

Covers the first acceptance criterion of Phase 1: a user can register, sign in
and be recognised afterwards (docs/architecture.md, section 50).
"""

from __future__ import annotations

from datetime import timedelta
from typing import Any

import jwt
from httpx import AsyncClient

from app.core.auth.tokens import create_access_token
from tests.conftest import (
    TEST_DATABASE_URL,  # noqa: F401 - imported for its side effect on os.environ
    auth_headers,
    register_user,
    unique_email,
    unique_username,
)

PASSWORD = "sup3r-secret"
NEW_PASSWORD = "another-secret"


async def register(client: AsyncClient, **overrides: Any):
    payload: dict[str, Any] = {
        "email": unique_email(),
        "username": unique_username(),
        "password": PASSWORD,
    }
    payload.update(overrides)
    return await client.post("/api/v1/auth/register", json=payload)


def closed_registration_settings() -> Any:
    from app.config import get_settings

    return get_settings().model_copy(update={"registration_mode": "invite"})


class TestRegister:
    async def test_creates_account_and_returns_a_session(self, client: AsyncClient) -> None:
        username = unique_username()

        response = await register(client, username=username, first_name="Ada", last_name="Lovelace")

        assert response.status_code == 201
        body = response.json()
        assert body["token_type"] == "bearer"
        assert body["access_token"]
        assert body["expires_at"]
        assert body["user"]["username"] == username
        assert body["user"]["first_name"] == "Ada"

    async def test_password_is_never_returned(self, client: AsyncClient) -> None:
        body = (await register(client)).json()

        assert "password" not in body["user"]
        assert "password_hash" not in body["user"]

    async def test_sets_an_httponly_cookie(self, client: AsyncClient) -> None:
        response = await register(client)

        set_cookie = response.headers["set-cookie"]
        assert "tt_access=" in set_cookie
        assert "HttpOnly" in set_cookie

    async def test_cookie_alone_authenticates(self, client: AsyncClient) -> None:
        await register(client)

        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 200

    async def test_rejects_a_short_password(self, client: AsyncClient) -> None:
        response = await register(client, password="short")

        assert response.status_code == 422

    async def test_rejects_a_malformed_email(self, client: AsyncClient) -> None:
        response = await register(client, email="not-an-email")

        assert response.status_code == 422

    async def test_rejects_a_duplicated_email(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email=email)

        response = await register(client, email=email)

        assert response.status_code == 409
        assert response.json()["error"]["code"] == "conflict"

    async def test_rejects_a_duplicated_username_in_any_case(self, client: AsyncClient) -> None:
        username = unique_username()
        await register(client, username=username)

        response = await register(client, username=username.upper())

        assert response.status_code == 409

    async def test_registration_can_be_closed(self, client: AsyncClient, monkeypatch) -> None:
        monkeypatch.setattr("app.core.auth.api.get_settings", closed_registration_settings)

        response = await register(client)

        assert response.status_code == 403
        assert response.json()["error"]["code"] == "registration_closed"


class TestLogin:
    async def test_accepts_email(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email=email)

        response = await client.post(
            "/api/v1/auth/login", json={"login": email, "password": PASSWORD}
        )

        assert response.status_code == 200
        assert response.json()["access_token"]

    async def test_accepts_username(self, client: AsyncClient) -> None:
        username = unique_username()
        await register(client, username=username)

        response = await client.post(
            "/api/v1/auth/login", json={"login": username, "password": PASSWORD}
        )

        assert response.status_code == 200

    async def test_email_match_is_case_insensitive(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email=email)

        response = await client.post(
            "/api/v1/auth/login", json={"login": email.upper(), "password": PASSWORD}
        )

        assert response.status_code == 200

    async def test_wrong_password_is_rejected(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email=email)

        response = await client.post(
            "/api/v1/auth/login", json={"login": email, "password": "wrong-password"}
        )

        assert response.status_code == 401
        assert response.json()["error"]["code"] == "invalid_credentials"

    async def test_unknown_account_looks_exactly_like_a_wrong_password(
        self, client: AsyncClient
    ) -> None:
        """Login must not be usable to enumerate accounts."""
        email = unique_email()
        await register(client, email=email)

        wrong_password = await client.post(
            "/api/v1/auth/login", json={"login": email, "password": "wrong-password"}
        )
        unknown_user = await client.post(
            "/api/v1/auth/login", json={"login": unique_email(), "password": PASSWORD}
        )

        assert wrong_password.status_code == unknown_user.status_code == 401
        assert wrong_password.json() == unknown_user.json()

    async def test_records_last_login(self, client: AsyncClient) -> None:
        email = unique_email()
        await register(client, email=email)

        await client.post("/api/v1/auth/login", json={"login": email, "password": PASSWORD})
        profile = await client.get("/api/v1/users/me")

        assert profile.json()["last_login_at"] is not None


class TestSession:
    async def test_me_requires_authentication(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me")

        assert response.status_code == 401
        assert response.headers.get("www-authenticate") == "Bearer"

    async def test_rejects_a_garbage_token(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/auth/me", headers=auth_headers("nonsense"))

        assert response.status_code == 401

    async def test_rejects_a_token_signed_with_another_key(self, client: AsyncClient) -> None:
        # Long enough for HS256, otherwise PyJWT warns about key strength and the
        # warning obscures the point of the test.
        forged = jwt.encode(
            {
                "sub": "00000000-0000-0000-0000-000000000000",
                "type": "access",
                "exp": 9_999_999_999,
            },
            "a-different-signing-key-of-adequate-length",
            algorithm="HS256",
        )

        response = await client.get("/api/v1/auth/me", headers=auth_headers(forged))

        assert response.status_code == 401

    async def test_rejects_an_expired_token(self, client: AsyncClient) -> None:
        session = await register_user(client)
        expired, _ = create_access_token(session["user"]["id"], expires_delta=timedelta(seconds=-1))

        response = await client.get("/api/v1/auth/me", headers=auth_headers(expired))

        assert response.status_code == 401
        assert "expired" in response.json()["error"]["message"].lower()

    async def test_logout_expires_the_cookie(self, client: AsyncClient) -> None:
        await register(client)

        response = await client.post("/api/v1/auth/logout")

        assert response.status_code == 204
        set_cookie = response.headers["set-cookie"]
        assert "tt_access=" in set_cookie
        assert "Max-Age=0" in set_cookie or set_cookie.startswith("tt_access=;")


class TestProfile:
    async def test_profile_is_returned(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.get(
            "/api/v1/users/me", headers=auth_headers(session["access_token"])
        )

        assert response.status_code == 200
        assert response.json()["id"] == session["user"]["id"]
        assert response.json()["is_superuser"] is False

    async def test_profile_can_be_updated(self, client: AsyncClient) -> None:
        session = await register_user(client)

        response = await client.patch(
            "/api/v1/users/me",
            json={"first_name": "Grace"},
            headers=auth_headers(session["access_token"]),
        )

        assert response.status_code == 200
        assert response.json()["first_name"] == "Grace"


class TestChangePassword:
    async def test_requires_the_current_password(self, client: AsyncClient) -> None:
        session = await register_user(client)
        headers = auth_headers(session["access_token"])

        wrong = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": "nope", "new_password": NEW_PASSWORD},
            headers=headers,
        )
        right = await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=headers,
        )

        assert wrong.status_code == 422
        assert right.status_code == 204

    async def test_new_password_replaces_the_old_one(self, client: AsyncClient) -> None:
        session = await register_user(client)
        email = session["user"]["email"]
        await client.post(
            "/api/v1/auth/change-password",
            json={"current_password": PASSWORD, "new_password": NEW_PASSWORD},
            headers=auth_headers(session["access_token"]),
        )

        with_old = await client.post(
            "/api/v1/auth/login", json={"login": email, "password": PASSWORD}
        )
        with_new = await client.post(
            "/api/v1/auth/login", json={"login": email, "password": NEW_PASSWORD}
        )

        assert with_old.status_code == 401
        assert with_new.status_code == 200
