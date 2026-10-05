from __future__ import annotations

import pytest
from fastapi import APIRouter

from app.core.modules import (
    ModuleBundle,
    ModuleDependencyError,
    ModuleError,
    ModuleManager,
    ModuleManifest,
    ModuleState,
)


def manifest(module_id: str, *, dependencies: tuple[str, ...] = ()) -> ModuleManifest:
    return ModuleManifest(
        id=module_id,
        name=module_id.title(),
        dependencies=dependencies,
        permissions=(f"{module_id}.view",),
        events=(f"{module_id}.created",),
    )


def bundle(module_id: str, *, dependencies: tuple[str, ...] = ()) -> ModuleBundle:
    return ModuleBundle(manifest=manifest(module_id, dependencies=dependencies))


class TestManifest:
    def test_invalid_id_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ModuleManifest(id="Tasks", name="Tasks")

    def test_self_dependency_is_rejected(self) -> None:
        with pytest.raises(ValueError):
            ModuleManifest(id="tasks", name="Tasks", dependencies=("tasks",))

    def test_missing_dependencies(self) -> None:
        subject = manifest("kanban", dependencies=("tasks",))
        assert subject.missing_dependencies({"tasks"}) == set()
        assert subject.missing_dependencies(set()) == {"tasks"}


class TestModuleManager:
    def test_register_and_enable(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("tasks"))

        assert manager.get("tasks").state is ModuleState.DISCOVERED

        manager.enable("tasks")
        assert manager.enabled[0].state is ModuleState.ENABLED
        assert manager.permissions == {"tasks.view"}

    def test_duplicate_registration_is_rejected(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("tasks"))
        with pytest.raises(ModuleError):
            manager.register(bundle("tasks"))

    def test_resolve_order_follows_dependencies(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("tasks"))
        manager.register(bundle("kanban", dependencies=("tasks",)))
        manager.register(bundle("crm"))
        for module_id in ("tasks", "kanban", "crm"):
            manager.enable(module_id)

        order = [module.manifest.id for module in manager.resolve_order()]

        assert order.index("tasks") < order.index("kanban")

    def test_disabled_dependency_breaks_resolution(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("tasks"))
        manager.register(bundle("kanban", dependencies=("tasks",)))
        manager.enable("kanban")

        with pytest.raises(ModuleDependencyError):
            manager.resolve_order()

    def test_circular_dependency_is_detected(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("a", dependencies=("b",)))
        manager.register(bundle("b", dependencies=("a",)))
        manager.enable("a")
        manager.enable("b")

        with pytest.raises(ModuleDependencyError):
            manager.resolve_order()

    async def test_bootstrap_mounts_routes_and_registers_handlers(self) -> None:
        router = APIRouter()

        @router.get("/ping")
        async def ping() -> dict[str, str]:
            return {"pong": "ok"}

        manager = ModuleManager()
        manager.register(
            ModuleBundle(
                manifest=manifest("tasks"),
                api_router=router,
                event_handlers=(("tasks.created", lambda event: None),),
            )
        )
        manager.enable("tasks")

        from fastapi import FastAPI

        app = FastAPI()
        app.state.api_v1_prefix = "/api/v1"
        manager.bootstrap(app)

        assert manager.bus.subscription_count == 1
        assert app.url_path_for("ping") == "/api/v1/ping"

    def test_describe_reports_state(self) -> None:
        manager = ModuleManager()
        manager.register(bundle("tasks"))
        manager.register(bundle("crm"))
        manager.enable("tasks")

        described = {item["id"]: item for item in manager.describe()}

        assert described["tasks"]["state"] == "enabled"
        assert described["crm"]["state"] == "discovered"
