"""Authorization service.

Permission checks always run in the context of an organization, because an
organization is the isolation boundary (docs/architecture.md, section 10).
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError
from app.core.organizations.models import OrganizationMember
from app.core.permissions.roles import (
    OrganizationRole,
    grants,
    outranks,
)
from app.core.users.models import User
from app.database.helpers import fetch_one


class AuthorizationService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_role(self, *, user_id: UUID, organization_id: UUID) -> OrganizationRole | None:
        stmt = select(OrganizationMember.role).where(
            OrganizationMember.user_id == user_id,
            OrganizationMember.organization_id == organization_id,
        )
        return await fetch_one(self._session, stmt)

    async def require_member(self, *, user: User, organization_id: UUID) -> OrganizationRole:
        """Return the caller's role or raise 403/404."""
        if user.is_superuser:
            return OrganizationRole.OWNER

        role = await self.get_role(user_id=user.id, organization_id=organization_id)
        if role is None:
            # 404 rather than 403 would hide existence; 403 is the honest answer
            # because the organization is genuinely visible but not accessible.
            raise PermissionDeniedError("You are not a member of this organization")
        return role

    async def require_permission(
        self,
        *,
        user: User,
        organization_id: UUID,
        permission: str,
    ) -> OrganizationRole:
        role = await self.require_member(user=user, organization_id=organization_id)
        if not grants(role, permission):
            raise PermissionDeniedError(
                f"Permission '{permission}' is required for this action",
                details={"required": permission, "role": str(role)},
            )
        return role

    async def require_manage_member(
        self,
        *,
        user: User,
        organization_id: UUID,
        target_user_id: UUID,
        target_role: OrganizationRole,
        new_role: OrganizationRole | None = None,
    ) -> OrganizationRole:
        """Only a strictly higher role may modify a member.

        Changing your *own* role is allowed, but only downwards - upwards would
        be privilege escalation and needs the same rank check as anybody else.
        Self-service is what lets "I am the only owner and want to step down"
        reach the state guard in the organization service, where the actionable
        answer lives: add another owner first.
        """
        actor_role = await self.require_permission(
            user=user,
            organization_id=organization_id,
            permission="organization.members.manage",
        )

        if target_user_id == user.id:
            if new_role is not None and not outranks(actor_role, new_role):
                raise PermissionDeniedError(
                    "You cannot raise your own role",
                    details={"actor_role": str(actor_role), "requested_role": str(new_role)},
                )
            return actor_role

        if not outranks(actor_role, target_role):
            raise PermissionDeniedError(
                "You cannot modify a member with an equal or higher role",
                details={"actor_role": str(actor_role), "target_role": str(target_role)},
            )
        return actor_role
