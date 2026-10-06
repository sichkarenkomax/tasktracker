from __future__ import annotations

import pytest
from asgi_lifespan import LifespanManager
from httpx import ASGITransport, AsyncClient

from app.config import Settings
from app.main import create_app


class TestSystemEndpoint:
    async def test_exposes_module_registry(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system")

        assert response.status_code == 200
        body = response.json()

        assert body["api_prefix"] == "/api/v1"
        assert isinstance(body["modules"], list)
        assert isinstance(body["permissions"], list)

    async def test_discovered_task_module_is_enabled_by_default(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system")
        modules = {item["id"]: item for item in response.json()["modules"]}

        assert "tasks" in modules
        assert modules["tasks"]["state"] == "enabled"
        assert modules["tasks"]["dependencies"] == []

    async def test_declared_permissions_are_exposed(self, client: AsyncClient) -> None:
        response = await client.get("/api/v1/system")
        permissions = response.json()["permissions"]

        assert "task.view" in permissions
        assert "task.create" in permissions

    async def test_core_permissions_are_exposed_separately(self, client: AsyncClient) -> None:
        """Core owns its own catalogue; modules declare theirs in the manifest."""
        response = await client.get("/api/v1/system")
        by_source = response.json()["permissions_by_source"]

        assert "project.create" in by_source["core"]
        assert "task.create" in by_source["modules"]["tasks"]
        assert "project.create" not in by_source["modules"]["tasks"]


class TestOpenAPI:
    async def test_schema_is_generated(self, client: AsyncClient) -> None:
        # Served under /api/* so that the reverse proxy reaches it; at /docs the
        # SPA would answer instead.
        response = await client.get("/api/openapi.json")

        assert response.status_code == 200
        paths = response.json()["paths"]
        assert "/health" in paths
        assert "/api/v1/system" in paths
        assert "/api/v1/auth/login" in paths
        assert "/api/v1/organizations" in paths
        assert "/api/v1/projects" in paths

    async def test_docs_can_be_switched_off(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A deployment that does not want to describe its surface can hide it."""
        monkeypatch.setattr("app.main.get_settings", lambda: Settings(api_docs_enabled=False))
        disabled = create_app()

        async with LifespanManager(disabled):
            transport = ASGITransport(app=disabled)
            async with AsyncClient(transport=transport, base_url="http://testserver") as http:
                assert (await http.get("/api/docs")).status_code == 404
                assert (await http.get("/api/openapi.json")).status_code == 404
                # The API itself is unaffected.
                assert (await http.get("/health")).status_code == 200
