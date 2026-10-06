"""Introspection endpoint for the platform and its module registry."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request

from app import __version__
from app.config import Settings
from app.core.modules import ModuleManager
from app.core.permissions import registry as permission_registry

router = APIRouter(tags=["system"])


@router.get("/system", summary="Platform info and module registry state")
async def system_info(request: Request) -> dict[str, Any]:
    settings: Settings = request.app.state.settings
    modules: ModuleManager = request.app.state.modules

    catalogue = permission_registry.catalogue(modules.permissions)
    return {
        "name": settings.app_name,
        "version": __version__,
        "environment": settings.app_env,
        "api_prefix": settings.api_v1_prefix,
        "modules": modules.describe(),
        # Flat list of everything grantable: Core permissions plus whatever the
        # enabled modules declare.
        "permissions": sorted(catalogue),
        "permissions_by_source": permission_registry.describe(modules),
        "events": modules.bus.event_names,
    }
