"""Files API.

Uploading, downloading and the three storage limits. Bytes are handed out only
through here, with a membership check on every request - there is no public
static route for uploads, which is the difference between a portal and a
directory listing.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Response, UploadFile, status
from fastapi import File as FormFile
from sqlalchemy import select

from app.config import get_settings
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.errors import NotFoundError, PermissionDeniedError, ValidationError
from app.core.files.models import StorageQuota
from app.core.files.schemas import (
    FileRead,
    MyQuotaRead,
    QuotaRead,
    QuotaWrite,
    UploadLimits,
)
from app.core.files.service import FileService, UploadRequest
from app.core.files.storage import FileStorage, build_storage
from app.core.permissions.service import AuthorizationService
from app.core.settings.service import SettingsService

router = APIRouter(tags=["files"])


@lru_cache(maxsize=4)
def _storage_for(root: Path) -> FileStorage:
    """One storage object per root.

    Resolved per request rather than at import, because the root comes from the
    environment and a test - or an S3 module registering itself later - has to be
    able to change it. The cache keeps that from rebuilding a wrapper per request.
    """
    return build_storage(root)


def _service(session: SessionDep) -> FileService:
    return FileService(session, _storage_for(get_settings().uploads_dir))


async def _organization_settings(session: SessionDep, organization_id: UUID) -> dict[str, Any]:
    return await SettingsService(session).read(organization_id)


@router.get(
    "/files/limits",
    response_model=UploadLimits,
    summary="What this portal accepts and how much room is left",
)
async def read_limits(
    organization_id: UUID, user: CurrentUser, session: SessionDep
) -> UploadLimits:
    """Read before uploading.

    The client cannot know the size cap or the remaining room without asking, and
    it should not have to guess: a limit enforced only at the end of an upload is
    a limit the person discovers when the file is already on the wire.
    """
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.view"
    )
    settings = await _organization_settings(session, organization_id)
    service = _service(session)
    state = await service.effective_quota(organization_id, user.id, settings)

    portal_limit = int(settings.get("storage_quota_bytes") or 0)
    used_bytes = await service.used_in_organization(organization_id)

    # Two limits can bite: the portal's total and the person's own. The client
    # needs the smaller one, so the answer is the room that actually exists.
    personal = state.limit_bytes - state.used_bytes if state.limit_bytes is not None else None
    overall = portal_limit - used_bytes if portal_limit else None
    candidates = [value for value in (personal, overall) if value is not None]

    return UploadLimits(
        max_file_size_bytes=int(settings.get("max_file_size_bytes") or 0),
        storage_quota_bytes=portal_limit,
        used_bytes=used_bytes,
        remaining_bytes=max(min(candidates), 0) if candidates else None,
    )


@router.post(
    "/files",
    response_model=FileRead,
    status_code=status.HTTP_201_CREATED,
    summary="Upload a file",
)
async def upload_file(
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
    file: Annotated[UploadFile, FormFile()],
) -> FileRead:
    settings = await _organization_settings(session, organization_id)
    row = await _service(session).upload(
        organization_id=organization_id,
        user_id=user.id,
        settings=settings,
        request=UploadRequest(
            filename=file.filename or "file",
            content_type=file.content_type or "application/octet-stream",
            # The whole file is read into memory: sizes are capped in megabytes
            # (and by the quota), and a streaming writer would have to undo a
            # half-finished write if the quota turned out to be full afterwards.
            data=await file.read(),
        ),
    )
    await session.commit()
    return FileRead.model_validate(row)


@router.get("/files/quota/me", response_model=MyQuotaRead, summary="My storage allowance")
async def read_my_quota(
    organization_id: UUID, user: CurrentUser, session: SessionDep
) -> MyQuotaRead:
    settings = await _organization_settings(session, organization_id)
    state = await _service(session).effective_quota(organization_id, user.id, settings)
    return MyQuotaRead(
        used_bytes=state.used_bytes,
        limit_bytes=state.limit_bytes,
        quota_source=state.source,
    )


@router.get("/files/quotas", response_model=list[QuotaRead], summary="Configured allowances")
async def list_quotas(
    organization_id: UUID, user: CurrentUser, session: SessionDep
) -> list[QuotaRead]:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.settings.manage"
    )
    stmt = select(StorageQuota).where(StorageQuota.organization_id == organization_id)
    rows = (await session.scalars(stmt)).all()
    return [QuotaRead.model_validate(row) for row in rows]


@router.put(
    "/files/quotas",
    response_model=QuotaRead,
    summary="Set a department's or a person's allowance",
)
async def set_quota(
    organization_id: UUID,
    payload: QuotaWrite,
    user: CurrentUser,
    session: SessionDep,
) -> QuotaRead:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.settings.manage"
    )
    if (payload.department_id is None) == (payload.user_id is None):
        raise ValidationError("Name exactly one subject: a department or a person")

    stmt = select(StorageQuota).where(StorageQuota.organization_id == organization_id)
    existing = (await session.scalars(stmt)).all()
    row = next(
        (
            candidate
            for candidate in existing
            if (payload.user_id is not None and candidate.user_id == payload.user_id)
            or (
                payload.department_id is not None
                and candidate.department_id == payload.department_id
            )
        ),
        None,
    )
    if row is None:
        row = StorageQuota(organization_id=organization_id)
        session.add(row)
    row.department_id = payload.department_id
    row.user_id = payload.user_id
    row.limit_bytes = payload.limit_bytes
    await session.commit()
    return QuotaRead.model_validate(row)


@router.delete(
    "/files/quotas/{quota_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove an allowance",
)
async def delete_quota(
    quota_id: UUID, organization_id: UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.settings.manage"
    )
    stmt = select(StorageQuota).where(
        StorageQuota.id == quota_id, StorageQuota.organization_id == organization_id
    )
    row = await session.scalar(stmt)
    if row is None:
        raise NotFoundError("No such quota in this organization")
    await session.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


# The two routes below are declared after every literal one above on purpose:
# `/files/{file_id}` would otherwise match `/files/quotas` first and try to read
# "quotas" as a UUID. Order is the whole fix, so the comment is here.


@router.get("/files/{file_id}", summary="Download a file")
async def download_file(
    file_id: UUID,
    organization_id: UUID,
    user: CurrentUser,
    session: SessionDep,
) -> Response:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.view"
    )
    service = _service(session)
    row = await service.get(organization_id, file_id)
    data = await service.read(row)
    return Response(
        content=data,
        media_type=row.content_type,
        headers={
            # Always as an attachment, never inline: these bytes came from a
            # browser upload and are served from our own origin, where an inline
            # HTML or SVG would be our page, not the uploader's.
            "Content-Disposition": f'attachment; filename="{row.filename}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.delete(
    "/files/{file_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete a file",
)
async def delete_file(
    file_id: UUID, organization_id: UUID, user: CurrentUser, session: SessionDep
) -> Response:
    await AuthorizationService(session).require_permission(
        user=user, organization_id=organization_id, permission="organization.view"
    )
    service = _service(session)
    row = await service.get(organization_id, file_id)
    if row.owner_id != user.id and not user.is_superuser:
        # Reading is a tenant-wide permission; removing is the uploader's own
        # file, because a shared attachment is removed by the person who put it
        # there or by somebody who can administer the portal.
        raise PermissionDeniedError("Only the uploader or a portal administrator may delete this")
    await service.delete(row)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
