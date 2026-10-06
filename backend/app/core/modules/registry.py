"""Module discovery.

On Phase 0 modules ship with the platform, so discovery is a filesystem walk
over ``app.modules``. Importing third-party code from disk, ZIP archives or a
remote registry is explicitly out of scope for the MVP
(docs/architecture.md, section 24).

A module package may provide:

``manifest.py``
    ``MANIFEST: ModuleManifest`` - **required**.
``api.py``
    ``API_ROUTER: APIRouter`` - optional.
``events.py``
    ``EVENT_HANDLERS: tuple[tuple[str, EventHandler], ...]`` - optional.
"""

from __future__ import annotations

import importlib
import logging
import pkgutil
from dataclasses import dataclass, field
from types import ModuleType
from typing import Any

from fastapi import APIRouter

from app.core.events.bus import EventHandler
from app.core.modules.manifest import InvalidManifest, ModuleManifest

logger = logging.getLogger(__name__)

DEFAULT_PACKAGE = "app.modules"


@dataclass(frozen=True, slots=True)
class ModuleBundle:
    """Everything a module contributes to the platform."""

    manifest: ModuleManifest
    api_router: APIRouter | None = None
    event_handlers: tuple[tuple[str, EventHandler], ...] = field(default=())
    errors: tuple[str, ...] = field(default=())


def discover_modules(package: str = DEFAULT_PACKAGE) -> list[ModuleBundle]:
    """Import every submodule of `package` and collect its manifest."""
    try:
        root = importlib.import_module(package)
    except ModuleNotFoundError:
        logger.warning("modules.discovery_skipped package=%s reason=not_found", package)
        return []

    locations = getattr(root, "__path__", None)
    if locations is None:  # pragma: no cover - defensive
        logger.warning("modules.discovery_skipped package=%s reason=not_a_package", package)
        return []

    bundles: list[ModuleBundle] = []
    for module_info in sorted(pkgutil.iter_modules(locations), key=lambda info: info.name):
        if module_info.name.startswith("_"):
            continue
        bundle = _load_module(f"{package}.{module_info.name}")
        if bundle is not None:
            bundles.append(bundle)

    logger.info(
        "modules.discovered package=%s count=%d",
        package,
        len(bundles),
    )
    return bundles


def import_module_packages(package: str = DEFAULT_PACKAGE) -> list[str]:
    """Import every module package without reading its manifest.

    Alembic autogenerate needs module-owned models registered on
    ``Base.metadata`` even for modules that are disabled at runtime, so this is
    deliberately separate from :func:`discover_modules`.
    """
    try:
        root = importlib.import_module(package)
    except ModuleNotFoundError:
        logger.warning("modules.import_skipped package=%s reason=not_found", package)
        return []

    locations = getattr(root, "__path__", None)
    if locations is None:  # pragma: no cover - defensive
        return []

    imported: list[str] = []
    for module_info in sorted(pkgutil.iter_modules(locations), key=lambda info: info.name):
        if module_info.name.startswith("_"):
            continue
        module_path = f"{package}.{module_info.name}"
        try:
            importlib.import_module(module_path)
        except Exception:  # pragma: no cover - a broken module must not kill boot
            logger.exception("modules.import_failed module=%s", module_path)
            continue
        imported.append(module_path)
    return imported


def _load_module(module_path: str) -> ModuleBundle | None:
    try:
        importlib.import_module(module_path)
    except Exception:  # pragma: no cover - a broken module must not kill boot
        logger.exception("modules.import_failed module=%s", module_path)
        return None

    manifest = _load_manifest(module_path)
    if manifest is None:
        return None

    api_router = _optional_attribute(f"{module_path}.api", "API_ROUTER", APIRouter)
    event_handlers = _optional_attribute(f"{module_path}.events", "EVENT_HANDLERS", tuple)

    return ModuleBundle(
        manifest=manifest,
        api_router=api_router,
        event_handlers=tuple(event_handlers or ()),
    )


def _load_manifest(module_path: str) -> ModuleManifest | None:
    manifest_module = _optional_module(f"{module_path}.manifest")
    manifest: Any = getattr(manifest_module, "MANIFEST", None) if manifest_module else None

    if manifest is None:
        logger.error("modules.manifest_missing module=%s", module_path)
        return None
    if not isinstance(manifest, ModuleManifest):
        logger.error(
            "modules.manifest_invalid module=%s reason=wrong_type",
            module_path,
        )
        return None
    try:
        # Re-run validation: manifests are usually constructed at import time.
        manifest.to_dict()
    except InvalidManifest as exc:  # pragma: no cover - defensive
        logger.error("modules.manifest_invalid module=%s reason=%s", module_path, exc)
        return None
    return manifest


def _optional_module(module_path: str) -> ModuleType | None:
    try:
        return importlib.import_module(module_path)
    except ModuleNotFoundError:
        return None
    except Exception:  # pragma: no cover - defensive
        logger.exception("modules.import_failed module=%s", module_path)
        return None


def _optional_attribute(module_path: str, attribute: str, expected: type) -> Any:
    module = _optional_module(module_path)
    if module is None:
        return None
    value = getattr(module, attribute, None)
    if value is None:
        return None
    if not isinstance(value, expected):
        logger.error(
            "modules.attribute_invalid module=%s attribute=%s expected=%s",
            module_path,
            attribute,
            getattr(expected, "__name__", expected),
        )
        return None
    return value
