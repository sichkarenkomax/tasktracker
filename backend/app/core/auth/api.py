"""Authentication API: register, login, logout, session."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Response, status

from app.config import get_settings
from app.core.auth.dependencies import CurrentUser, SessionDep
from app.core.auth.schemas import (
    ChangePasswordRequest,
    LoginRequest,
    RegisterRequest,
    TokenResponse,
    UserSummary,
)
from app.core.auth.tokens import create_access_token
from app.core.dependencies import EventBusDep
from app.core.users.models import User
from app.core.users.repository import UserRepository
from app.core.users.service import UserService

router = APIRouter(prefix="/auth", tags=["auth"])


def _set_auth_cookie(response: Response, token: str, expires_at: datetime) -> None:
    settings = get_settings()
    response.set_cookie(
        key=settings.auth_cookie_name,
        value=token,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
        expires=expires_at,
        path="/",
    )


def _clear_auth_cookie(response: Response) -> None:
    settings = get_settings()
    response.delete_cookie(
        key=settings.auth_cookie_name,
        path="/",
        secure=settings.auth_cookie_secure,
        samesite=settings.auth_cookie_samesite,
    )


def _issue(user: User, response: Response) -> TokenResponse:
    token, expires_at = create_access_token(user.id)
    _set_auth_cookie(response, token, expires_at)
    return TokenResponse(
        access_token=token,
        expires_at=expires_at,
        user=UserSummary.model_validate(user),
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create an account and sign in",
)
async def register(
    payload: RegisterRequest,
    response: Response,
    session: SessionDep,
    bus: EventBusDep,
) -> TokenResponse:
    service = UserService(UserRepository(session), bus)
    user = await service.register(
        email=payload.email,
        username=payload.username,
        password=payload.password,
        first_name=payload.first_name,
        last_name=payload.last_name,
        registration_open=get_settings().registration_open,
    )
    await session.commit()
    return _issue(user, response)


@router.post("/login", response_model=TokenResponse, summary="Sign in")
async def login(
    payload: LoginRequest,
    response: Response,
    session: SessionDep,
    bus: EventBusDep,
) -> TokenResponse:
    service = UserService(UserRepository(session), bus)
    user = await service.authenticate(login=payload.login, password=payload.password)
    await session.commit()
    return _issue(user, response)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, summary="Sign out")
async def logout(response: Response) -> None:
    _clear_auth_cookie(response)


@router.get("/me", response_model=UserSummary, summary="Current session user")
async def me(user: CurrentUser) -> UserSummary:
    return UserSummary.model_validate(user)


@router.post("/change-password", status_code=status.HTTP_204_NO_CONTENT)
async def change_password(
    payload: ChangePasswordRequest,
    user: CurrentUser,
    session: SessionDep,
    bus: EventBusDep,
) -> None:
    await UserService(UserRepository(session), bus).change_password(
        user, current=payload.current_password, new=payload.new_password
    )
    await session.commit()
