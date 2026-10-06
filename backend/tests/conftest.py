"""Shared test fixtures.

The suite runs against a real PostgreSQL, not SQLite: the schema uses JSONB,
native UUIDs and ``CHECK``-constrained enums, so a fake database would not
prove anything (docs/architecture.md, section 45).

Set ``TEST_DATABASE_URL`` or start the throwaway database with
``make test-up``. Every test truncates all tables first, so ordering never
matters.
"""

from __future__ import annotations

import os
import uuid
from collections.abc import AsyncIterator, Iterator
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]

#: Where `make test-up` publishes the throwaway database.
DEFAULT_TEST_DATABASE_URL = (
    "postgresql+asyncpg://tasktracker:tasktracker@localhost:55432/tasktracker_test"
)

# The application settings are read at import time, so the redirect to the test
# database has to happen before anything under `app.` is imported.
TEST_DATABASE_URL = os.environ.get("TEST_DATABASE_URL", DEFAULT_TEST_DATABASE_URL)
os.environ["DATABASE_URL"] = TEST_DATABASE_URL
# Cookies are only transmitted over HTTPS otherwise, which the test client is not.
os.environ.setdefault("AUTH_COOKIE_SECURE", "false")
os.environ.setdefault("SECRET_KEY", "test-secret-key-not-used-in-production")
os.environ.setdefault("APP_ENV", "development")
os.environ.setdefault("LOG_JSON", "false")
os.environ.setdefault("LOG_LEVEL", "WARNING")

import pytest  # noqa: E402
from asgi_lifespan import LifespanManager  # noqa: E402
from httpx import ASGITransport, AsyncClient  # noqa: E402
from sqlalchemy import text  # noqa: E402

from app.core.organizations.schemas import slugify  # noqa: E402
from app.database.base import Base  # noqa: E402
from app.database.session import engine  # noqa: E402
from app.main import create_app  # noqa: E402


def unique_email(prefix: str = "user") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12]}@example.com"


def unique_username(prefix: str = "user") -> str:
    return f"{prefix}_{uuid.uuid4().hex[:10]}"


def unique_suffix() -> str:
    return uuid.uuid4().hex[:8]


@pytest.fixture(scope="session")
def migrated_database() -> Iterator[None]:
    """Apply the real Alembic migrations once, and tear the schema down after.

    Running the actual migration chain (rather than ``create_all``) means a
    broken migration fails the suite instead of only failing in production.
    """
    from alembic.config import Config

    from alembic import command

    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "alembic"))

    # Alembic opens its own event loop (``asyncio.run``), so this fixture has to
    # stay synchronous - hence there is no separate reachability probe here.
    # An unreachable database surfaces as the failure below.
    try:
        command.upgrade(config, "head")
    except Exception as exc:
        pytest.fail(
            f"Alembic could not apply migrations to {TEST_DATABASE_URL}: {exc}\n\n"
            "Start it with `make test-up`, or point TEST_DATABASE_URL elsewhere."
        )

    try:
        yield
    finally:
        command.downgrade(config, "base")


@pytest.fixture(autouse=True)
async def clean_database(migrated_database: None) -> AsyncIterator[None]:
    """Truncate every table before each test."""
    table_names = sorted(Base.metadata.tables)
    if table_names:
        quoted = ", ".join(f'"{name}"' for name in table_names)
        async with engine.begin() as connection:
            await connection.execute(text(f"TRUNCATE {quoted} CASCADE"))

    yield


@pytest.fixture
async def client() -> AsyncIterator[AsyncClient]:
    """HTTP client bound to the real application, lifespan included."""
    app = create_app()
    async with LifespanManager(app):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://testserver") as http:
            yield http


async def register_user(
    client: AsyncClient, *, prefix: str = "user", password: str = "sup3r-secret"
) -> dict[str, Any]:
    """Create an account and return the token payload."""
    response = await client.post(
        "/api/v1/auth/register",
        json={
            "email": unique_email(prefix),
            "username": unique_username(prefix),
            "password": password,
            "first_name": "Test",
            "last_name": "User",
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def auth_headers(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


async def create_organization(
    client: AsyncClient, token: str, *, name: str = "Acme", slug: str | None = None
) -> dict[str, Any]:
    """Create an organization.

    Slugs are unique platform-wide, so a unique one is generated unless the test
    asks for a specific value. The display name keeps its default so that tests
    can assert on it.
    """
    payload: dict[str, Any] = {
        "name": name,
        "slug": slug if slug is not None else f"{slugify(name)}-{unique_suffix()}",
    }
    response = await client.post("/api/v1/organizations", json=payload, headers=auth_headers(token))
    assert response.status_code == 201, response.text
    return response.json()


@pytest.fixture
async def owner(client: AsyncClient) -> dict[str, Any]:
    """A registered user that already owns an organization."""
    session = await register_user(client, prefix="owner")
    token = session["access_token"]
    organization = await create_organization(client, token)
    return {"token": token, "user": session["user"], "organization": organization}


@pytest.fixture
async def outsider(client: AsyncClient) -> dict[str, Any]:
    """A registered user that belongs to no organization of its own."""
    session = await register_user(client, prefix="outsider")
    return {"token": session["access_token"], "user": session["user"]}
