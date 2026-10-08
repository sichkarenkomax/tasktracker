"""Settings storage: organization-wide, and per user."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import ForeignKey, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class OrganizationSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single per-organization setting override."""

    __tablename__ = "organization_settings"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (UniqueConstraint("organization_id", "key", name="uq_org_setting_org_key"),)


class UserSetting(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A single personal setting for one member of one organization.

    Scoped by organization as well as by user, because a personal setting means
    something only inside the tenant it was set in: "my week starts on Monday" is
    a statement about this portal, and a person who belongs to two gets to decide
    it separately in each. The user foreign key cascades so that deleting an
    account takes its preferences with it rather than leaving them addressable.
    """

    __tablename__ = "user_settings"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    key: Mapped[str] = mapped_column(String(100), nullable=False)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)

    __table_args__ = (
        UniqueConstraint("organization_id", "user_id", "key", name="uq_user_setting_org_user_key"),
    )
