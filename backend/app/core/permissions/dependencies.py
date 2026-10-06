"""FastAPI dependencies for authorization.

``require_permission`` reads the organization from the route's path parameters
and refuses to guess. A route that wants a permission check must therefore be
organization-scoped by construction, which is what keeps a permission from ever
being evaluated against the wrong tenant (docs/architecture.md, section 10).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import cast
from uuid import UUID

from fastapi import Request

from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.errors import PermissionDeniedError
from app.core.permissions.service import AuthorizationService
from app.core.users.models import User


def organization_id_from_path(request: Request) -> str:
    raw = request.path_params.get("organization_id")
    if raw is None:
        raise PermissionDeniedError(
            "Organization context is missing from the route",
            details={"hint": "declare organization_id as a path parameter"},
        )
    return cast(str, raw)


def require_permission(permission: str) -> Callable[..., Awaitable[User]]:
    """Dependency factory: ``Depends(require_permission("project.update"))``."""

    async def dependency(
        request: Request,
        user: CurrentUser,
        session: SessionDep,
    ) -> User:
        organization_id = UUID(organization_id_from_path(request))
        await AuthorizationService(session).require_permission(
            user=user,
            organization_id=organization_id,
            permission=permission,
        )
        return user

    return dependency


__all__ = ["organization_id_from_path", "require_permission"]
