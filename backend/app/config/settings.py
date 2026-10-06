"""Application configuration.

Every setting is environment driven so that the same image can run in
development and production. Values are read once and cached.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
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
    #: Interactive API documentation at /api/docs. Turn off to stop describing
    #: the whole surface to anyone who can reach the port.
    api_docs_enabled: bool = True

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
    #: Signs JWT access tokens. Generated and persisted on first start when left
    #: at the placeholder (see app.config.secret_key).
    secret_key: str = INSECURE_DEFAULT_SECRET
    #: Where an auto-generated key is kept. Must live on a persistent volume.
    secret_key_file: Path = Path("/var/lib/tasktracker/secret_key")
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
        """True when no real signing key is configured (unset or placeholder)."""
        return not self.secret_key or self.secret_key == INSECURE_DEFAULT_SECRET

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

    def resolve_secret_key(self) -> None:
        """Adopt a persisted or freshly generated signing key.

        An empty ``SECRET_KEY`` counts as unset: an empty string is a perfectly
        valid HMAC key, which is exactly why it must never reach the signer.
        """
        if not self.uses_insecure_secret:
            return
        from app.config.secret_key import load_or_create_secret_key

        self.secret_key, _ = load_or_create_secret_key(
            secret_key=self.secret_key, secret_key_file=self.secret_key_file
        )

    def validate_runtime(self) -> None:
        """Resolve the signing key, then fail fast if it is still unusable.

        ``resolve_secret_key`` either returns a strong key or raises, so the check
        below is a backstop rather than the primary guard.
        """
        self.resolve_secret_key()
        if self.uses_insecure_secret:  # pragma: no cover - defensive
            raise RuntimeError(
                "SECRET_KEY is empty or still the development placeholder and could not be "
                "persisted. Generate a random value (for example: python -c "
                '"import secrets; print(secrets.token_urlsafe(48))") and set it in the '
                "environment."
            )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
