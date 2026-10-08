"""File service: the one place that decides what may be stored.

Everything that stores bytes goes through here - the avatars of stage 2.3, the
attachments of 2.20, whatever a module uploads later. Modules do not touch a
filesystem or an S3 client (`docs/architecture.md`, section 43); they call this.

The rules it enforces, in the order they are checked:

1. **The uploader is a member of the tenant** the file lands in.
2. **The type is on the list.** A whitelist, not a blacklist: a new kind of file
   should have to be added deliberately.
3. **The size is within the portal's limit** (`max_file_size_bytes`), which is
   what stops one request from filling a volume.
4. **The portal has room** in total (`storage_quota_bytes`).
5. **The uploader's own allowance has room**, where their allowance is their own
   limit if they have one, otherwise their department's, otherwise nothing.

The precedence in rule 5 is the user's: a person's setting outranks their
department's. The reason is that the department limit is a number somebody set
for a group without asking, while the person has been asked.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import PermissionDeniedError, ValidationError
from app.core.files.models import File, StorageQuota
from app.core.files.storage import FileStorage
from app.core.organizations.models import OrganizationMember

#: Types accepted in v1. Deliberately short, and deliberately without SVG: it is
#: an image by MIME type and a script by content, and serving it from our own
#: origin would run it. Adding a type here is a one-line decision with a security
#: consequence, not a formality.
ALLOWED_CONTENT_TYPES: frozenset[str] = frozenset(
    {
        "image/png",
        "image/jpeg",
        "image/gif",
        "image/webp",
        "application/pdf",
        "text/plain",
        "text/csv",
    }
)


@dataclass(frozen=True)
class UploadRequest:
    filename: str
    content_type: str
    data: bytes


@dataclass(frozen=True)
class QuotaState:
    """How much room is left, and whose limit decided that."""

    used_bytes: int
    limit_bytes: int | None
    source: str

    @property
    def exceeded(self) -> bool:
        return self.limit_bytes is not None and self.used_bytes >= self.limit_bytes


class FileService:
    def __init__(self, session: AsyncSession, storage: FileStorage) -> None:
        self._session = session
        self._storage = storage

    # --- reading ------------------------------------------------------------

    async def get(self, organization_id: UUID, file_id: UUID) -> File:
        stmt = select(File).where(File.id == file_id, File.organization_id == organization_id)
        row = await self._session.scalar(stmt)
        if row is None:
            # One message for "not yours" and "not there": a caller who can tell
            # the two apart can enumerate other tenants' files by id.
            raise PermissionDeniedError("No such file in this organization")
        return row

    async def read(self, row: File) -> bytes:
        return await self._storage.read(row.storage_key)

    # --- writing ------------------------------------------------------------

    async def upload(
        self,
        *,
        organization_id: UUID,
        user_id: UUID,
        settings: dict[str, Any],
        request: UploadRequest,
    ) -> File:
        await self._require_member(organization_id, user_id)

        if request.content_type not in ALLOWED_CONTENT_TYPES:
            raise ValidationError(
                f"Files of type {request.content_type} cannot be uploaded",
                details={"allowed": sorted(ALLOWED_CONTENT_TYPES)},
            )

        max_size = int(settings.get("max_file_size_bytes") or 0)
        if max_size and len(request.data) > max_size:
            raise ValidationError(
                f"File is larger than the {max_size} byte limit this portal allows",
                details={"size": len(request.data), "max_file_size_bytes": max_size},
            )

        await self._check_portal_room(organization_id, settings, len(request.data))
        await self._check_personal_room(organization_id, user_id, settings, len(request.data))

        key = storage_key(organization_id, uuid4())
        await self._storage.save(key, request.data)

        row = File(
            organization_id=organization_id,
            owner_id=user_id,
            filename=request.filename[:255],
            content_type=request.content_type,
            size_bytes=len(request.data),
            storage_key=key,
        )
        self._session.add(row)
        await self._session.flush()
        return row

    async def delete(self, row: File) -> None:
        await self._storage.delete(row.storage_key)
        await self._session.delete(row)
        await self._session.flush()

    # --- the rules ----------------------------------------------------------

    async def _require_member(self, organization_id: UUID, user_id: UUID) -> OrganizationMember:
        stmt = select(OrganizationMember).where(
            OrganizationMember.organization_id == organization_id,
            OrganizationMember.user_id == user_id,
        )
        member = await self._session.scalar(stmt)
        if member is None:
            raise PermissionDeniedError("You are not a member of this organization")
        return member

    async def used_in_organization(self, organization_id: UUID) -> int:
        stmt = select(func.coalesce(func.sum(File.size_bytes), 0)).where(
            File.organization_id == organization_id
        )
        return int(await self._session.scalar(stmt) or 0)

    async def _used_by_user(self, organization_id: UUID, user_id: UUID) -> int:
        stmt = select(func.coalesce(func.sum(File.size_bytes), 0)).where(
            File.organization_id == organization_id,
            File.owner_id == user_id,
        )
        return int(await self._session.scalar(stmt) or 0)

    async def _used_by_department(self, organization_id: UUID, department_id: UUID) -> int:
        """Everything stored by the people in a department.

        A join rather than a stored counter: the members of a department change,
        and a counter would then have to be moved between people by hand every
        time somebody is reassigned - which is exactly the bookkeeping that turns
        a limit into a lie.
        """
        stmt = select(func.coalesce(func.sum(File.size_bytes), 0)).where(
            File.organization_id == organization_id,
            File.owner_id.in_(
                select(OrganizationMember.user_id).where(
                    OrganizationMember.organization_id == organization_id,
                    OrganizationMember.department_id == department_id,
                )
            ),
        )
        return int(await self._session.scalar(stmt) or 0)

    async def _check_portal_room(
        self, organization_id: UUID, settings: dict[str, Any], incoming: int
    ) -> None:
        limit = int(settings.get("storage_quota_bytes") or 0)
        if not limit:
            return
        used = await self.used_in_organization(organization_id)
        if used + incoming > limit:
            raise ValidationError(
                "This portal has no room left in its storage quota",
                details={"used": used, "incoming": incoming, "storage_quota_bytes": limit},
            )

    async def effective_quota(
        self, organization_id: UUID, user_id: UUID, settings: dict[str, Any]
    ) -> QuotaState:
        """Whose allowance applies to this person, and how much of it is used.

        Own limit, then their department's, then nothing - a person always wins
        over the group they sit in, and a person in no department is limited only
        by the portal.
        """
        own = await self._quota_for_user(organization_id, user_id)
        if own is not None:
            return QuotaState(
                used_bytes=await self._used_by_user(organization_id, user_id),
                limit_bytes=own,
                source="user",
            )

        member = await self._require_member(organization_id, user_id)
        if member.department_id is not None:
            group = await self._quota_for_department(organization_id, member.department_id)
            if group is not None:
                return QuotaState(
                    used_bytes=await self._used_by_department(
                        organization_id, member.department_id
                    ),
                    limit_bytes=group,
                    source="department",
                )

        return QuotaState(
            used_bytes=await self._used_by_user(organization_id, user_id),
            limit_bytes=None,
            source="none",
        )

    async def _check_personal_room(
        self,
        organization_id: UUID,
        user_id: UUID,
        settings: dict[str, Any],
        incoming: int,
    ) -> None:
        state = await self.effective_quota(organization_id, user_id, settings)
        if state.limit_bytes is not None and state.used_bytes + incoming > state.limit_bytes:
            raise ValidationError(
                "This account has no room left in its storage quota",
                details={
                    "used": state.used_bytes,
                    "incoming": incoming,
                    "limit_bytes": state.limit_bytes,
                    "quota_source": state.source,
                },
            )

    async def _quota_for_user(self, organization_id: UUID, user_id: UUID) -> int | None:
        stmt = select(StorageQuota.limit_bytes).where(
            StorageQuota.organization_id == organization_id,
            StorageQuota.user_id == user_id,
        )
        limit = await self._session.scalar(stmt)
        return None if limit is None else int(limit)

    async def _quota_for_department(self, organization_id: UUID, department_id: UUID) -> int | None:
        stmt = select(StorageQuota.limit_bytes).where(
            StorageQuota.organization_id == organization_id,
            StorageQuota.department_id == department_id,
        )
        limit = await self._session.scalar(stmt)
        return None if limit is None else int(limit)


def storage_key(organization_id: UUID, file_id: UUID) -> str:
    """A key for one file, and the only place one is built.

    Two levels of fan-out under the tenant, then the id. The bytes of a file are
    found by looking up its id in the database, so nothing a request contains can
    influence where on disk anything lives.
    """
    flat = f"{organization_id.hex}"
    return f"{flat[:2]}/{organization_id.hex}/{file_id.hex[:2]}/{file_id.hex}"
