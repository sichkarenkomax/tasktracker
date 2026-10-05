"""Module Manager: registry, dependency order, wiring.

Responsibilities (docs/architecture.md, section 23):

* discover modules and validate their manifests;
* resolve dependency order;
* register routes, permissions and event handlers;
* keep module state so it can be reported through the API.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import StrEnum
from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, FastAPI

from app.core.events.bus import EventBus
from app.core.modules.manifest import ModuleManifest

if TYPE_CHECKING:  # pragma: no cover
    from app.core.modules.registry import ModuleBundle

logger = logging.getLogger(__name__)


class ModuleError(Exception):
    """Base class for module registry failures."""


class ModuleDependencyError(ModuleError):
    """Raised when module dependencies cannot be satisfied."""


class ModuleState(StrEnum):
    DISCOVERED = "discovered"
    ENABLED = "enabled"
    DISABLED = "disabled"
    FAILED = "failed"


@dataclass(slots=True)
class RegisteredModule:
    manifest: ModuleManifest
    bundle: ModuleBundle | None = None
    state: ModuleState = ModuleState.DISCOVERED
    error: str | None = None


@dataclass(slots=True)
class ModuleManager:
    """Holds every known module and wires the enabled ones into the app."""

    modules: dict[str, RegisteredModule] = field(default_factory=dict)
    bus: EventBus = field(default_factory=EventBus)
    _mounted: bool = False

    # -- registration ------------------------------------------------------
    def register(self, bundle: ModuleBundle) -> RegisteredModule:
        if bundle.manifest.id in self.modules:
            raise ModuleError(f"Module {bundle.manifest.id!r} is already registered")
        registered = RegisteredModule(manifest=bundle.manifest, bundle=bundle)
        self.modules[registered.manifest.id] = registered
        return registered

    def register_all(self, bundles: list[ModuleBundle]) -> None:
        for bundle in bundles:
            self.register(bundle)

    # -- state -------------------------------------------------------------
    def enable(self, module_id: str) -> None:
        self._set_state(module_id, ModuleState.ENABLED)

    def disable(self, module_id: str) -> None:
        self._set_state(module_id, ModuleState.DISABLED)

    def _set_state(self, module_id: str, state: ModuleState) -> None:
        registered = self.get(module_id)
        if registered.state in (ModuleState.FAILED,) and state is ModuleState.ENABLED:
            raise ModuleError(f"Module {module_id!r} failed to start: {registered.error}")
        registered.state = state

    def get(self, module_id: str) -> RegisteredModule:
        try:
            return self.modules[module_id]
        except KeyError as exc:
            raise ModuleError(f"Unknown module {module_id!r}") from exc

    @property
    def enabled(self) -> list[RegisteredModule]:
        return [m for m in self.modules.values() if m.state is ModuleState.ENABLED]

    @property
    def failed(self) -> list[RegisteredModule]:
        return [m for m in self.modules.values() if m.state is ModuleState.FAILED]

    # -- dependency resolution --------------------------------------------
    def resolve_order(self) -> list[RegisteredModule]:
        """Topologically sort the enabled modules by their dependencies."""
        enabled = {m.manifest.id: m for m in self.enabled}
        if not enabled:
            return []

        for module_id, registered in enabled.items():
            missing = registered.manifest.missing_dependencies(enabled)
            if missing:
                raise ModuleDependencyError(
                    f"Module {module_id!r} requires missing or disabled modules: "
                    f"{', '.join(sorted(missing))}"
                )

        ordered: list[RegisteredModule] = []
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(module_id: str, chain: tuple[str, ...]) -> None:
            if module_id in visited:
                return
            if module_id in visiting:
                cycle = " -> ".join((*chain, module_id))
                raise ModuleDependencyError(f"Circular module dependency: {cycle}")
            visiting.add(module_id)
            for dependency in enabled[module_id].manifest.dependencies:
                visit(dependency, (*chain, module_id))
            visiting.discard(module_id)
            visited.add(module_id)
            ordered.append(enabled[module_id])

        for module_id in sorted(enabled):
            visit(module_id, ())
        return ordered

    # -- wiring ------------------------------------------------------------
    def bootstrap(self, app: FastAPI) -> list[RegisteredModule]:
        """Wire enabled modules into the application (routes + events)."""
        if self._mounted:
            raise ModuleError("Module manager is already bootstrapped")

        try:
            ordered = self.resolve_order()
        except ModuleDependencyError as exc:
            logger.error("modules.bootstrap_failed reason=%s", exc)
            self.mark_failed(str(exc))
            raise

        router = APIRouter()
        for registered in ordered:
            bundle = registered.bundle
            if bundle is None:
                continue
            if bundle.api_router is not None:
                router.include_router(bundle.api_router, tags=[registered.manifest.id])
            for event_name, handler in bundle.event_handlers:
                self.bus.subscribe(event_name, handler, owner=registered.manifest.id)

        app.include_router(router, prefix=app.state.api_v1_prefix)
        self._mounted = True
        logger.info(
            "modules.bootstrap modules=%s permissions=%d event_handlers=%d",
            [m.manifest.id for m in ordered],
            len(self.permissions),
            self.bus.subscription_count,
        )
        return ordered

    def mark_failed(self, reason: str) -> None:
        for registered in self.modules.values():
            if registered.state is not ModuleState.DISABLED:
                registered.state = ModuleState.FAILED
                registered.error = reason

    # -- introspection -----------------------------------------------------
    @property
    def permissions(self) -> set[str]:
        return {perm for m in self.enabled for perm in m.manifest.permissions}

    def describe(self) -> list[dict[str, Any]]:
        return [
            {
                **module.manifest.to_dict(),
                "state": str(module.state),
                "error": module.error,
            }
            for module in sorted(self.modules.values(), key=lambda m: m.manifest.id)
        ]
