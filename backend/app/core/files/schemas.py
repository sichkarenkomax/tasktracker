"""File API schemas."""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.core.files.service import ALLOWED_CONTENT_TYPES


class FileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    organization_id: UUID
    owner_id: UUID
    filename: str
    content_type: str
    size_bytes: int
    created_at: datetime


class QuotaRead(BaseModel):
    """A configured allowance, as the settings screen lists them."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    department_id: UUID | None
    user_id: UUID | None
    limit_bytes: int


class QuotaWrite(BaseModel):
    """Set one subject's allowance. Exactly one subject must be named.

    Both are optional in the type and mandatory in the meaning: a request that
    names neither, or both, is refused rather than stored, because a row like
    that is a limit nobody could later explain.
    """

    department_id: UUID | None = None
    user_id: UUID | None = None
    limit_bytes: int = Field(ge=0)


class MyQuotaRead(BaseModel):
    """How much room the caller has left, and whose limit it is."""

    used_bytes: int
    limit_bytes: int | None
    quota_source: str


class UploadLimits(BaseModel):
    """What the client is allowed to send, so it does not have to guess.

    The browser needs the size cap before it starts reading a file, and the
    allowed types before it accepts one at all; both are server truth handed out
    rather than duplicated in the frontend.
    """

    max_file_size_bytes: int
    storage_quota_bytes: int
    used_bytes: int
    remaining_bytes: int | None
    allowed_content_types: list[str] = sorted(ALLOWED_CONTENT_TYPES)
