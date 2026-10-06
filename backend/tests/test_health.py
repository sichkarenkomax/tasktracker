from __future__ import annotations

from typing import Any

from httpx import AsyncClient


class TestHealth:
    async def test_liveness_is_dependency_free(self, client: AsyncClient) -> None:
        response = await client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"]
        assert body["version"]


class TestReadiness:
    async def test_reports_ready_when_database_is_up(
        self, client: AsyncClient, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr("app.api.health.check_database", _database_up)

        response = await client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"]["status"] == "up"

    async def test_reports_ready_against_a_real_database(self, client: AsyncClient) -> None:
        """No stubbing: the migrated test database is actually reachable."""
        response = await client.get("/health/ready")

        assert response.status_code == 200
        assert response.json()["checks"]["database"]["status"] == "up"

    async def test_returns_503_when_database_is_down(
        self, client: AsyncClient, monkeypatch: Any
    ) -> None:
        monkeypatch.setattr("app.api.health.check_database", _database_down)

        response = await client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


async def _database_up() -> tuple[bool, None]:
    return True, None


async def _database_down() -> tuple[bool, str]:
    return False, "connection refused"
