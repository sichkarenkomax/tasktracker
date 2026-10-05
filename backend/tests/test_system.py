from __future__ import annotations

from fastapi.testclient import TestClient


class TestSystemEndpoint:
    def test_exposes_module_registry(self, client: TestClient) -> None:
        response = client.get("/api/v1/system")

        assert response.status_code == 200
        body = response.json()

        assert body["api_prefix"] == "/api/v1"
        assert isinstance(body["modules"], list)
        assert isinstance(body["permissions"], list)

    def test_discovered_task_module_is_enabled_by_default(self, client: TestClient) -> None:
        modules = {item["id"]: item for item in client.get("/api/v1/system").json()["modules"]}

        assert "tasks" in modules
        assert modules["tasks"]["state"] == "enabled"
        assert modules["tasks"]["dependencies"] == []

    def test_declared_permissions_are_exposed(self, client: TestClient) -> None:
        permissions = client.get("/api/v1/system").json()["permissions"]

        assert "task.view" in permissions
        assert "task.create" in permissions


class TestOpenAPI:
    def test_schema_is_generated(self, client: TestClient) -> None:
        response = client.get("/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/health" in paths
        assert "/api/v1/system" in paths
