"""User model and lifecycle status."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, false
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.config import get_settings
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, value_enum


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class User(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "users"

    email: Mapped[str] = mapped_column(String(320), unique=True, nullable=False)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)

    # Never null, never returned by the API layer.
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    first_name: Mapped[str | None] = mapped_column(String(64))
    last_name: Mapped[str | None] = mapped_column(String(64))

    #: Which row of ``files`` serves as this person's picture - a reference,
    #: never a URL. The database thus knows that the file *is* an avatar,
    #: deleting the file clears the avatar (``ON DELETE SET NULL``) instead of
    #: leaving a link to nothing, and every read of the bytes is decided per
    #: request by a permission check (stage 2.3).
    avatar_file_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("files.id", ondelete="SET NULL"), index=True
    )

    #: A birthday, and nothing that could be told from it: no year, no zodiac,
    #: no "how old is he". A contact detail, shown or hidden by the same rule as
    #: the phones (stage 2.6), not a fact about the person that everything else
    #: may read. The date is stored whole rather than split into month and day
    #: because a year that was never given is exactly what a person withholds,
    #: and a nullable year in one column cannot be mistaken for 1970.
    birthday: Mapped[date | None] = mapped_column(Date)

    status: Mapped[UserStatus] = mapped_column(
        value_enum(UserStatus, name="user_status", length=16),
        nullable=False,
        default=UserStatus.ACTIVE,
        server_default=UserStatus.ACTIVE.value,
    )

    is_superuser: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=false(),
    )

    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    __table_args__ = (Index("ix_users_status", "status"),)

    def __repr__(self) -> str:
        return f"<User {self.username}>"

    @property
    def avatar_url(self) -> str | None:
        """Where this person's picture is served from - computed, never stored.

        The file id doubles as a cache key: a new picture is a new file and so
        a new URL, which is what keeps a browser from showing the old face
        after an upload. The endpoint behind the URL decides, per request,
        whether the viewer may see the file's organization at all.
        """
        if self.avatar_file_id is None:
            return None
        prefix = get_settings().api_v1_prefix
        return f"{prefix}/users/{self.id}/avatar?v={self.avatar_file_id}"


class UserPhone(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One phone number, with whatever the owner wants to say about it.

    A separate table rather than a column because people have more than one and
    the number alone is not the whole answer: "work", "the one for the workshop
    in Lyon", "call after six". The comment belongs to the number, not to the
    person, so it moves with it when the number is edited or removed.

    Several rows per user, ordered by ``created_at`` and nothing else: which
    number is the main one is a thing a person states by writing it first, not
    a flag this schema would then have to explain.
    """

    __tablename__ = "user_phones"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    number: Mapped[str] = mapped_column(String(32), nullable=False)

    comment: Mapped[str | None] = mapped_column(String(120))

    __table_args__ = (Index("ix_user_phones_user_id_created_at", "user_id", "created_at"),)

    def __repr__(self) -> str:
        return f"<UserPhone {self.number}>"
