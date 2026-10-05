"""Application configuration.

Every setting is environment driven so that the same image can run in
development and production. Values are read once and cached.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

#: Placeholder that must be replaced before running in production.
INSECURE_DEFAULT_SECRET = "dev-insecure-change-me"

AppEnv = Literal["development", "staging", "production"]


def split_csv(raw: str) -> list[str]:
    """Parse a comma-separated environment value into a clean list."""
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # --- Application -------------------------------------------------------
    app_name: str = "TaskTracker"
    app_env: AppEnv = "development"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # --- Logging -----------------------------------------------------------
    log_level: str = "INFO"
    log_json: bool = True

    # --- CORS --------------------------------------------------------------
    # Comma-separated. Empty means "same origin only".
    cors_origins: str = ""

    # --- Database ----------------------------------------------------------
    database_url: str = "postgresql+asyncpg://tasktracker:tasktracker@localhost:5432/tasktracker"
    db_echo: bool = False

    # --- Modules -----------------------------------------------------------
    # Comma-separated. Empty means "every discovered module is enabled".
    enabled_modules: str = ""

    # --- Security ----------------------------------------------------------
    #: Signs JWT access tokens. MUST be overridden in production.
    secret_key: str = INSECURE_DEFAULT_SECRET
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 60 * 24
    #: Issued as an httpOnly cookie in addition to the JSON body, so the SPA
    #: never has to keep a token in JavaScript (see docs/architecture.md, 44).
    auth_cookie_name: str = "tt_access"
    auth_cookie_secure: bool = True
    auth_cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    #: Who may create new accounts. "anyone" suits an open self-hosted
    #: instance, "invite" suits a closed one.
    registration_mode: Literal["anyone", "invite"] = "anyone"
    max_page_size: int = 100
    default_page_size: int = 25

    # --- Reverse proxy -----------------------------------------------------
    site_address: str = ":80"

    # --- Derived views -----------------------------------------------------
    @property
    def cors_origin_list(self) -> list[str]:
        return split_csv(self.cors_origins)

    @property
    def enabled_module_list(self) -> list[str]:
        return split_csv(self.enabled_modules)

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def uses_insecure_secret(self) -> bool:
        return self.secret_key == INSECURE_DEFAULT_SECRET

    @property
    def registration_open(self) -> bool:
        return self.registration_mode == "anyone"

    @model_validator(mode="after")
    def _check_cookie_security(self) -> Settings:
        # SameSite=None is only honoured by browsers over HTTPS, and a cookie
        # without Secure is rejected in that combination.
        if self.auth_cookie_samesite == "none" and not self.auth_cookie_secure:
            raise ValueError("AUTH_COOKIE_SAMESITE=none requires AUTH_COOKIE_SECURE=true")
        return self

    def validate_runtime(self) -> None:
        """Fail fast on insecure production configuration."""
        if self.is_production and self.uses_insecure_secret:
            raise RuntimeError(
                "SECRET_KEY still holds the development placeholder. Generate a random "
                "value (for example: python -c \"import secrets; "
                "print(secrets.token_urlsafe(48))\") and set it in the environment."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
