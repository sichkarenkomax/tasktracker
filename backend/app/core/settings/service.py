"""Settings service.

Modules read and write organization settings through this interface rather
than touching the table, so the storage backend stays replaceable
(same principle as FileService, docs/architecture.md section 43).
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.core.settings.models import OrganizationSetting

#: Settings a module may declare. `default` is the value used when an
#: organization has no override stored.
SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "locale": {"type": "string", "default": "en"},
    "timezone": {"type": "string", "default": "UTC"},
    "date_format": {"type": "string", "default": "YYYY-MM-DD"},
    "week_starts_on": {"type": "integer", "default": 1},
    "task_auto_archive_days": {"type": "integer", "default": 0},
}


def defaults() -> dict[str, Any]:
    return {key: spec["default"] for key, spec in SETTING_DEFINITIONS.items()}


def definitions() -> dict[str, dict[str, Any]]:
    return dict(SETTING_DEFINITIONS)


class SettingsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, organization_id: UUID) -> dict[str, Any]:
        """Effective values: definitions merged with stored overrides."""
        stmt = select(OrganizationSetting).where(
            OrganizationSetting.organization_id == organization_id
        )
        rows = (await self._session.scalars(stmt)).all()
        values = defaults()
        values.update({row.key: row.value for row in rows})
        return values

    async def write(self, organization_id: UUID, values: dict[str, Any]) -> dict[str, Any]:
        unknown = sorted(set(values) - set(SETTING_DEFINITIONS))
        if unknown:
            raise NotFoundError(
                f"Unknown setting(s): {', '.join(unknown)}",
                details={"available": sorted(SETTING_DEFINITIONS)},
            )

        stmt = select(OrganizationSetting).where(
            OrganizationSetting.organization_id == organization_id
        )
        existing = {row.key: row for row in (await self._session.scalars(stmt)).all()}

        for key, value in values.items():
            row = existing.get(key)
            if row is None:
                self._session.add(
                    OrganizationSetting(organization_id=organization_id, key=key, value=value)
                )
            else:
                row.value = value
        await self._session.flush()
        return await self.read(organization_id)
