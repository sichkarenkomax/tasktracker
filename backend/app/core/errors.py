"""Domain-level errors.

Services raise these; a single FastAPI exception handler translates them into
HTTP responses. Keeping them framework-free is what lets a module be extracted
into a separate service later without rewriting its logic
(docs/architecture.md, section 5).
"""

from __future__ import annotations

from typing import Any


class DomainError(Exception):
    """Base class for all expected business errors."""

    status_code = 400
    code = "domain_error"

    def __init__(self, message: str, *, details: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.details = details or {}


class ValidationError(DomainError):
    status_code = 422
    code = "validation_error"


class NotFoundError(DomainError):
    status_code = 404
    code = "not_found"


class ConflictError(DomainError):
    status_code = 409
    code = "conflict"


class AuthenticationError(DomainError):
    status_code = 401
    code = "authentication_error"


class CredentialsError(AuthenticationError):
    code = "invalid_credentials"


class PermissionDeniedError(DomainError):
    status_code = 403
    code = "permission_denied"


class RegistrationClosedError(DomainError):
    status_code = 403
    code = "registration_closed"
