"""FastAPI application factory.

Wiring order matters:

1. configuration + logging;
2. module discovery, enable/disable according to ``ENABLED_MODULES``;
3. module bootstrap (routes, event handlers, permissions);
4. first-party routers (health, system).

Modules are mounted under ``/api/v1`` by the Module Manager itself, so a new
module never requires touching this file (docs/architecture.md, section 64).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import __version__
from app.api.health import router as health_router
from app.api.system import router as system_router
from app.config import get_settings
from app.core.logging import configure_logging
from app.core.modules import ModuleManager, discover_modules
from app.database.session import dispose_engine

logger = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        manager = ModuleManager()
        manager.register_all(discover_modules())

        allowlist = set(settings.enabled_module_list)
        for registered in manager.modules.values():
            if allowlist and registered.manifest.id not in allowlist:
                manager.disable(registered.manifest.id)
                logger.info(
                    "modules.disabled id=%s reason=not_in_enabled_modules",
                    registered.manifest.id,
                )
            else:
                manager.enable(registered.manifest.id)

        app.state.modules = manager
        manager.bootstrap(app)
        logger.info("app.started name=%s env=%s", settings.app_name, settings.app_env)

        try:
            yield
        finally:
            await dispose_engine()
            logger.info("app.stopped")

    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Modular self-hosted platform for team work management.",
        lifespan=lifespan,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
    )
    app.state.settings = settings
    app.state.api_v1_prefix = settings.api_v1_prefix

    origins = settings.cors_origin_list
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
    else:
        # Same-origin traffic goes through Caddy, so no CORS headers are needed.
        logger.info("cors.disabled reason=no_origins_configured")

    app.include_router(health_router)
    app.include_router(system_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
