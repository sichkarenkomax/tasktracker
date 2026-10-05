"""Liveness and readiness probes.

``/health`` stays dependency-free so that an orchestrator can distinguish
"process is alive" from "process cannot serve traffic"
(docs/architecture.md, section 49).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request, Response, status

from app import __version__
from app.database.session import check_database

router = APIRouter(tags=["system"])


@router.get("/health", summary="Liveness probe")
async def health(request: Request) -> dict[str, Any]:
    settings = request.app.state.settings
    return {
        "status": "ok",
        "service": settings.app_name,
        "environment": settings.app_env,
        "version": __version__,
    }


@router.get("/health/ready", summary="Readiness probe")
async def readiness(request: Request, response: Response) -> dict[str, Any]:
    database_ok, database_error = await check_database()
    modules = request.app.state.modules

    payload: dict[str, Any] = {
        "status": "ready" if database_ok else "not_ready",
        "version": __version__,
        "checks": {
            "database": {
                "status": "up" if database_ok else "down",
                "error": database_error,
            },
            "modules": {
                "total": len(modules.modules),
                "enabled": len(modules.enabled),
                "failed": len(modules.failed),
            },
        },
    }
    if not database_ok:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return payload
