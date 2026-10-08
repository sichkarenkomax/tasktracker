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
from app.core.settings.models import OrganizationSetting, UserSetting

#: Settings a module may declare. `default` is the value used when an
#: organization has no override stored.
SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "locale": {"type": "string", "default": "en"},
    "timezone": {"type": "string", "default": "UTC"},
    "date_format": {"type": "string", "default": "YYYY-MM-DD"},
    "week_starts_on": {"type": "integer", "default": 1},
    "task_auto_archive_days": {"type": "integer", "default": 0},
    # Files (stage 2.2). Zero means "no limit", which is the only honest default
    # for a self-hosted portal whose owner knows their own disk: a limit invented
    # here would be enforced the first time somebody tried to attach a file, and
    # the person hitting it would not be the person who chose the number. The
    # settings screen offers both, and per-department and per-person allowances
    # live in `storage_quotas` rather than here.
    "max_file_size_bytes": {"type": "integer", "default": 0},
    "storage_quota_bytes": {"type": "integer", "default": 0},
}

#: Personal settings, the same contract one level down: a key declared here is a
#: key the preferences screen may write, and a key it does not declare is refused
#: rather than stored.
#:
#: `locale` and `theme` are declared because they are the settings the screen
#: actually shows. In v1 they are *read* from the browser, not from here (stage
#: 1.1: the first paint must not wait on a round trip, and a preference nobody
#: else can see has no reason to live on a server yet) - declaring them keeps the
#: screen's vocabulary in one place, so moving a key to the server later is
#: changing where the value is read, not what the screen offers.
PERSONAL_SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "locale": {"type": "string", "default": "ru", "values": ["en", "ru"]},
    "theme": {"type": "string", "default": "gold", "values": ["gold", "blue"]},
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


def personal_defaults() -> dict[str, Any]:
    return {key: spec["default"] for key, spec in PERSONAL_SETTING_DEFINITIONS.items()}


def personal_definitions() -> dict[str, dict[str, Any]]:
    return dict(PERSONAL_SETTING_DEFINITIONS)


class PersonalSettingsService:
    """One member's settings inside one organization.

    Separate from `SettingsService` rather than a flag on it: the two have
    different owners, different authority (a person may always write their own,
    while an organization's settings need a permission), and different fallbacks
    - an organization falls back to its declared default, a person falls back to
    the default *and* to whatever the browser says, which the screen resolves.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def read(self, organization_id: UUID, user_id: UUID) -> dict[str, Any]:
        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id == user_id,
        )
        rows = (await self._session.scalars(stmt)).all()
        values = personal_defaults()
        values.update({row.key: row.value for row in rows})
        return values

    async def write(
        self, organization_id: UUID, user_id: UUID, values: dict[str, Any]
    ) -> dict[str, Any]:
        unknown = sorted(set(values) - set(PERSONAL_SETTING_DEFINITIONS))
        if unknown:
            raise NotFoundError(
                f"Unknown setting(s): {', '.join(unknown)}",
                details={"available": sorted(PERSONAL_SETTING_DEFINITIONS)},
            )

        stmt = select(UserSetting).where(
            UserSetting.organization_id == organization_id,
            UserSetting.user_id == user_id,
        )
        existing = {row.key: row for row in (await self._session.scalars(stmt)).all()}

        for key, value in values.items():
            row = existing.get(key)
            if row is None:
                self._session.add(
                    UserSetting(
                        organization_id=organization_id, user_id=user_id, key=key, value=value
                    )
                )
            else:
                row.value = value
        await self._session.flush()
        return await self.read(organization_id, user_id)
