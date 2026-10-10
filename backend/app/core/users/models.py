"""User model and lifecycle status."""

from __future__ import annotations

from datetime import date, datetime
from enum import StrEnum
from uuid import UUID

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, String, UniqueConstraint, false
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.config import get_settings
from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin, value_enum


class UserStatus(StrEnum):
    ACTIVE = "active"
    INVITED = "invited"
    DISABLED = "disabled"


class PhoneKind(StrEnum):
    """What a number is for (stage 2.8).

    A fixed list rather than free text, because a person's own words here are
    only ever a label the reader already knows: "рабочий", "домашний",
    "мобильный" are the three anybody writes, and "other" says the rest. Free
    text made this column a second comment field - and a comment field is
    where a phone number goes to be forgotten.
    """

    WORK = "work"
    HOME = "home"
    MOBILE = "mobile"
    OTHER = "other"


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

    #: When they were last *here* - the last request they made, not the last
    #: password they proved (stage 2.9). Written from ordinary API traffic,
    #: throttled to once a minute per person, and read by nobody who has not
    #: answered for it first: who may see it is the same question as who may see
    #: the contacts, with the same two settings deciding (see
    #: `users.visibility.Visibility`).
    last_seen: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

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
    """One phone number, and what it is for.

    A separate table rather than a column because people have more than one. The
    *kind* is a closed list (see :class:`PhoneKind`) and lives on the row, so it
    travels with its own number when that number is edited or removed.

    The number itself is stored in E.164 - digits with a leading ``+`` - which
    is the only form that is comparable, sortable and unambiguous. The mask that
    groups it for reading is a presentation detail (stage 2.8), and a database
    holding "+7 (900) 123-45-67" would sort by its punctuation and match nothing
    when somebody searches for a number they copied out of a printed ad.

    Several rows per user, ordered by ``created_at`` and nothing else: which
    number is the main one is a thing a person states by writing it first, not
    a flag this schema would then have to explain.
    """

    __tablename__ = "user_phones"

    user_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )

    number: Mapped[str] = mapped_column(String(32), nullable=False)

    #: The country the number is *read* in, ISO 3166-1 alpha-2 ("RU", "US").
    #: Nullable and defaulted to nothing on purpose: a number stored before this
    #: column existed has no country, and guessing one would put somebody else's
    #: number into a national format they never wrote. Such a row is shown in
    #: the international form, which is the one that cannot be misread.
    country: Mapped[str | None] = mapped_column(String(2))

    kind: Mapped[PhoneKind] = mapped_column(
        value_enum(PhoneKind, name="phone_kind", length=16),
        nullable=False,
        default=PhoneKind.WORK,
        server_default=PhoneKind.WORK.value,
    )

    #: One row per number per person, and the database says so rather than the
    #: service alone. "Work" and "mobile" for the same digits is not two numbers,
    #: it is one number stated twice, and a duplicate makes every list keyed by
    #: the number quietly drop one of them.
    __table_args__ = (
        Index("ix_user_phones_user_id_created_at", "user_id", "created_at"),
        UniqueConstraint("user_id", "number", name="uq_user_phones_user_id_number"),
    )

    def __repr__(self) -> str:
        return f"<UserPhone {self.number}>"
