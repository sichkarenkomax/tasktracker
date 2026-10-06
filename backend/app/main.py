"""FastAPI application factory.

Wiring order matters:

1. configuration + logging;
2. module discovery, enable/disable according to ``ENABLED_MODULES``;
3. module bootstrap (routes, event handlers, permissions);
4. Core routers, including the Activity projection subscriber;
5. first-party system routers (health, system).

Modules are mounted under ``/api/v1`` by the Module Manager itself, so a new
module never requires touching this file (docs/architecture.md, section 64).
"""

from __future__ import annotations

import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

from app import __version__
from app.api.health import router as health_router
from app.api.system import router as system_router
from app.config import get_settings
from app.core.activity.projector import ActivityProjector
from app.core.events.bus import SUCCESS_CEILING
from app.core.exception_handlers import register_exception_handlers
from app.core.logging import configure_logging
from app.core.modules import ModuleManager, discover_modules
from app.core.router import router as core_router
from app.database.session import SessionFactory, dispose_engine

logger = logging.getLogger(__name__)


class DomainEventDispatchMiddleware(BaseHTTPMiddleware):
    """Publishes buffered domain events once the request has succeeded.

    Domain errors are turned into responses rather than raised past the
    middleware, so the status code is what tells us whether the transaction was
    committed. A 4xx/5xx response means the work was rolled back and its events
    must be dropped - otherwise the Activity feed would record changes that
    never happened.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        bus = request.app.state.modules.bus
        buffer = bus.start_buffer()
        try:
            response = await call_next(request)
        except BaseException:
            bus.discard_buffer(buffer)
            raise

        if response.status_code >= SUCCESS_CEILING:
            bus.discard_buffer(buffer)
            return response

        failures = await bus.flush_buffer(buffer)
        if failures:
            # The response is already produced; a broken projection must not
            # turn a committed write into an error for the client.
            logger.warning("core.events_flushed_with_failures count=%d", len(failures))
        return response


def create_app() -> FastAPI:
    settings = get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_json)
    settings.validate_runtime()

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

        # Core subscribes to every event, which is how Activity stays module
        # agnostic (docs/architecture.md, sections 19 and 21).
        manager.bus.subscribe_all(ActivityProjector(SessionFactory), owner="core.activity")
        logger.info("core.activity_subscribed handlers=%d", manager.bus.subscription_count)

        logger.info("app.started name=%s env=%s", settings.app_name, settings.app_env)

        try:
            yield
        finally:
            await dispose_engine()
            logger.info("app.stopped")

    # The interactive docs live under the API prefix on purpose: Caddy routes
    # `/api/*` to the backend and everything else to the SPA, so `/docs` would
    # silently return the frontend instead of Swagger UI.
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        summary="Modular self-hosted platform for team work management.",
        lifespan=lifespan,
        docs_url="/api/docs" if settings.api_docs_enabled else None,
        redoc_url="/api/redoc" if settings.api_docs_enabled else None,
        openapi_url="/api/openapi.json" if settings.api_docs_enabled else None,
    )
    app.state.settings = settings
    app.state.api_v1_prefix = settings.api_v1_prefix

    register_exception_handlers(app)
    # Added last so that it wraps the routers: events must be flushed after the
    # route committed its transaction.
    app.add_middleware(DomainEventDispatchMiddleware)

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
    app.include_router(core_router, prefix=settings.api_v1_prefix)
    app.include_router(system_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
