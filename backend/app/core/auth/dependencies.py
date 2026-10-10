"""FastAPI dependencies for authentication.

These are the only sanctioned way for routers to obtain the current user or a
database session. Permission enforcement lives in
``app.core.permissions.dependencies`` so that authentication does not depend on
the authorization layer.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.auth.tokens import decode_access_token
from app.core.errors import AuthenticationError
from app.core.users import presence
from app.core.users.models import User
from app.database.session import get_session

# auto_error=False so that the httpOnly cookie set by the API is accepted too.
bearer_scheme = HTTPBearer(auto_error=False)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


def get_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> str:
    if credentials is not None and credentials.scheme.lower() == "bearer":
        return credentials.credentials

    cookie = request.cookies.get(get_settings().auth_cookie_name)
    if cookie:
        return cookie

    raise AuthenticationError("Authentication required")


async def get_current_user(
    request: Request,
    token: Annotated[str, Depends(get_token)],
    session: SessionDep,
) -> User:
    claims = decode_access_token(token)
    user = await session.get(User, claims.user_id)
    if user is None:
        raise AuthenticationError("Account no longer exists")
    # "Last seen" is written here because this is the one place every
    # authenticated request passes through (stage 2.9). The function is
    # throttled to one write a minute per person, so the cost is bounded no
    # matter how many rows a screen renders.
    await presence.record(user, session)
    request.state.user = user
    return user


CurrentUser = Annotated[User, Depends(get_current_user)]

__all__ = [
    "CurrentUser",
    "SessionDep",
    "get_current_user",
    "get_token",
]
