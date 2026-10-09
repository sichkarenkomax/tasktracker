"""File storage models."""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import BigInteger, ForeignKey, Index, String, text
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import Uuid

from app.database.base import Base, TimestampMixin, UUIDPrimaryKeyMixin


class File(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """One stored file, addressed by its id and never by its path.

    The row is the only thing that knows where the bytes are: ``storage_key`` is
    generated on the server and never built from anything the caller sent, so a
    request cannot address a file by guessing a path. Deleting the account that
    uploaded it takes its files with it, which is the point of storing the owner
    rather than a name.
    """

    __tablename__ = "files"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    owner_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    #: What the uploader called it, kept for display. Never used as a path.
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_key: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)


class StorageQuota(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    """A storage allowance for one department or one person.

    Three levels of limit exist and only two of them are rows here: the portal's
    own total lives in the organization settings, because it is a property of the
    installation like every other organization setting. A department's and a
    person's are rows, because they are overrides - and an override has to be
    removable and attributable.

    Exactly one subject per row, which is what the check constraint below says: a
    row with neither or both would be a quota nobody could reason about.
    """

    __tablename__ = "storage_quotas"

    organization_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("organizations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    department_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("org_departments.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[UUID | None] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    #: Bytes this subject may store in total. Zero means "no limit of its own",
    #: which is how a department that has never been given a quota behaves.
    limit_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)

    # One allowance per subject - a partial unique index rather than a composite
    # one, because a composite would treat the NULL in the unused column as
    # equal-but-unknown and let a second row for the same department in.
    __table_args__ = (
        Index(
            "uq_storage_quotas_department",
            "organization_id",
            "department_id",
            unique=True,
            postgresql_where=text("department_id IS NOT NULL"),
        ),
        Index(
            "uq_storage_quotas_user",
            "organization_id",
            "user_id",
            unique=True,
            postgresql_where=text("user_id IS NOT NULL"),
        ),
    )
