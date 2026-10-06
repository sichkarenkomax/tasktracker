"""Translation of domain errors into HTTP responses.

Services never raise ``HTTPException``; this handler is the single place that
knows about status codes (docs/architecture.md, section 5 - keeping services
framework-free is what allows a module to be extracted later).
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.core.errors import AuthenticationError, DomainError

logger = logging.getLogger(__name__)

_UNAUTHORIZED_HEADERS = {"WWW-Authenticate": "Bearer"}


def error_payload(code: str, message: str, details: dict[str, Any]) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, "details": details}}


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def handle_domain_error(_request: Request, exc: DomainError) -> JSONResponse:
        headers = _UNAUTHORIZED_HEADERS if isinstance(exc, AuthenticationError) else None
        if exc.status_code >= 500:  # pragma: no cover - defensive
            logger.exception("domain_error code=%s", exc.code)
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(exc.code, exc.message, exc.details),
            headers=headers,
        )
