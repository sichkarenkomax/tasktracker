"""JWT access tokens.

Deliberately stateless: no session table, no Redis. Logout revokes the token
by rotating `SECRET_KEY`, which is the honest trade-off for an MVP
(docs/architecture.md, section 39 - queues are not introduced yet).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt

from app.config import get_settings
from app.core.errors import CredentialsError

TOKEN_TYPE = "access"


class TokenClaims(dict[str, Any]):
    @property
    def user_id(self) -> UUID:
        return UUID(str(self["sub"]))

    @property
    def token_type(self) -> str:
        return str(self.get("type", TOKEN_TYPE))


def create_access_token(
    user_id: UUID,
    *,
    extra_claims: dict[str, Any] | None = None,
    expires_delta: timedelta | None = None,
) -> tuple[str, datetime]:
    """Return (token, expires_at)."""
    settings = get_settings()
    now = datetime.now(UTC)
    expires_at = now + (expires_delta or timedelta(minutes=settings.access_token_ttl_minutes))

    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TOKEN_TYPE,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
        "iss": settings.app_name,
        **(extra_claims or {}),
    }
    token = jwt.encode(payload, settings.secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_at


def decode_access_token(token: str) -> TokenClaims:
    settings = get_settings()
    try:
        payload = jwt.decode(
            token,
            settings.secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.app_name,
            options={"require": ["exp", "sub", "type"]},
        )
    except jwt.ExpiredSignatureError as exc:
        raise CredentialsError("Session expired, please sign in again") from exc
    except jwt.InvalidTokenError as exc:
        raise CredentialsError("Invalid authentication token") from exc

    if payload.get("type") != TOKEN_TYPE:
        raise CredentialsError("Invalid authentication token")
    return TokenClaims(payload)
