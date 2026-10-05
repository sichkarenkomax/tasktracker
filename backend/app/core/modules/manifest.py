"""Module manifest contract."""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

MODULE_ID_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class InvalidManifest(ValueError):
    """Raised when a manifest violates the module contract."""


@dataclass(frozen=True, slots=True)
class ModuleManifest:
    """Declarative description of a single module.

    Attributes
    ----------
    id:
        Stable, unique module identifier (also used as URL namespace).
    name:
        Human readable name shown in the UI.
    version:
        SemVer string.
    dependencies:
        Ids of other modules that must be enabled first.
    permissions:
        Permission strings the module declares (docs/architecture.md, section 25).
    routes:
        Extra route prefixes the module wants Caddy/the frontend to know about.
    events:
        Event names the module publishes. Purely declarative on Phase 0 - it
        documents the contract and feeds documentation.
    """

    id: str
    name: str
    version: str = "0.0.0"
    description: str = ""
    dependencies: tuple[str, ...] = ()
    permissions: tuple[str, ...] = ()
    routes: tuple[str, ...] = ()
    events: tuple[str, ...] = ()
    frontend: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        if not MODULE_ID_PATTERN.match(self.id):
            raise InvalidManifest(
                f"Module id must match {MODULE_ID_PATTERN.pattern!r}, got {self.id!r}"
            )
        if not self.name.strip():
            raise InvalidManifest(f"Module {self.id!r} must declare a non-empty name")
        if self.id in self.dependencies:
            raise InvalidManifest(f"Module {self.id!r} cannot depend on itself")

    def missing_dependencies(self, available: Iterable[str]) -> set[str]:
        known = set(available)
        return {dep for dep in self.dependencies if dep not in known}

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "version": self.version,
            "description": self.description,
            "dependencies": list(self.dependencies),
            "permissions": list(self.permissions),
            "routes": list(self.routes),
            "events": list(self.events),
            "frontend": list(self.frontend),
        }
