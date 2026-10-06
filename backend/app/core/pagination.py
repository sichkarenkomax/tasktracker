"""Pagination parameters shared by every list endpoint.

One rule for page size across the whole API: the default and the ceiling come
from settings (``DEFAULT_PAGE_SIZE`` / ``MAX_PAGE_SIZE``) rather than from
hardcoded numbers repeated in every router. A caller asking for 10_000 rows is
clamped instead of being refused, which keeps a mistyped ``limit`` from turning
into a 422 on an otherwise valid request.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Annotated

from fastapi import Depends, Query

from app.config import get_settings


@dataclass(frozen=True, slots=True)
class PageParams:
    limit: int
    offset: int


def page_params(
    limit: Annotated[
        int | None, Query(ge=1, description="Page size, clamped to the maximum")
    ] = None,
    offset: Annotated[int, Query(ge=0, description="Rows to skip")] = 0,
) -> PageParams:
    settings = get_settings()
    return PageParams(
        limit=min(
            limit if limit is not None else settings.default_page_size, settings.max_page_size
        ),
        offset=offset,
    )


#: FastAPI only recognises a dependency inside ``Annotated`` when it is an
#: explicit ``Depends``. A bare callable is treated as ordinary annotation
#: metadata, which silently turned ``page`` into a *required request body* on
#: every list endpoint - a 422 in reply to a perfectly ordinary GET.


PageDep = Annotated[PageParams, Depends(page_params)]
