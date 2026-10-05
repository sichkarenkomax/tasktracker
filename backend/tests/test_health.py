from __future__ import annotations

from fastapi.testclient import TestClient


class TestHealth:
    def test_liveness_is_dependency_free(self, client: TestClient) -> None:
        response = client.get("/health")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ok"
        assert body["service"]
        assert body["version"]


class TestReadiness:
    def test_reports_ready_when_database_is_up(self, client: TestClient, monkeypatch) -> None:
        monkeypatch.setattr("app.api.health.check_database", _database_up)

        response = client.get("/health/ready")

        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ready"
        assert body["checks"]["database"]["status"] == "up"

    def test_returns_503_when_database_is_down(self, client: TestClient, monkeypatch) -> None:
        monkeypatch.setattr("app.api.health.check_database", _database_down)

        response = client.get("/health/ready")

        assert response.status_code == 503
        assert response.json()["status"] == "not_ready"


async def _database_up() -> tuple[bool, None]:
    return True, None


async def _database_down() -> tuple[bool, str]:
    return False, "connection refused"
