"""Signing key resolution.

The rule under test: the application must never sign tokens with a value that
is published in the repository, and the operator must not have to prepare one
before the first start.
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.config.secret_key import load_or_create_secret_key
from app.config.settings import INSECURE_DEFAULT_SECRET, Settings


class TestPrecedence:
    def test_an_explicit_key_is_used_and_no_file_is_touched(self, tmp_path: Path) -> None:
        target = tmp_path / "secret_key"

        key, origin = load_or_create_secret_key(secret_key="explicit-key", secret_key_file=target)

        assert key == "explicit-key"
        assert origin is None
        assert not target.exists()

    def test_a_generated_key_is_reused_on_the_next_start(self, tmp_path: Path) -> None:
        target = tmp_path / "secret_key"

        first, origin = load_or_create_secret_key(
            secret_key=INSECURE_DEFAULT_SECRET, secret_key_file=target
        )
        second, _ = load_or_create_secret_key(secret_key="", secret_key_file=target)

        assert first != INSECURE_DEFAULT_SECRET
        assert second == first
        assert origin == target

    def test_a_generated_key_is_long_and_random(self, tmp_path: Path) -> None:
        key, _ = load_or_create_secret_key(secret_key="", secret_key_file=tmp_path / "secret_key")

        assert len(key) >= 64
        other, _ = load_or_create_secret_key(secret_key="", secret_key_file=tmp_path / "other")
        assert other != key

    def test_surrounding_whitespace_in_the_file_is_ignored(self, tmp_path: Path) -> None:
        target = tmp_path / "secret_key"
        target.write_text("  stored-key\n", encoding="utf-8")

        key, _ = load_or_create_secret_key(secret_key="", secret_key_file=target)

        assert key == "stored-key"


class TestFailureIsLoud:
    def test_an_unwritable_location_names_both_ways_out(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "app.config.secret_key.Path.write_text",
            lambda *_args, **_kwargs: (_ for _ in ()).throw(OSError("read-only file system")),
        )

        with pytest.raises(RuntimeError, match="SECRET_KEY"):
            load_or_create_secret_key(
                secret_key="", secret_key_file=tmp_path / "nested" / "secret_key"
            )

    def test_generating_is_reported_as_a_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        with caplog.at_level(logging.WARNING):
            load_or_create_secret_key(secret_key="", secret_key_file=tmp_path / "secret_key")

        assert "secret_key.generated" in caplog.text

    def test_reusing_a_stored_key_is_not_a_warning(
        self, tmp_path: Path, caplog: pytest.LogCaptureFixture
    ) -> None:
        target = tmp_path / "secret_key"
        load_or_create_secret_key(secret_key="", secret_key_file=target)
        caplog.clear()

        with caplog.at_level(logging.WARNING):
            load_or_create_secret_key(secret_key="", secret_key_file=target)

        assert caplog.text == ""


class TestSettings:
    def test_empty_and_placeholder_both_count_as_unset(self) -> None:
        assert Settings(secret_key="").uses_insecure_secret
        assert Settings(secret_key=INSECURE_DEFAULT_SECRET).uses_insecure_secret
        assert not Settings(secret_key="something-real").uses_insecure_secret

    def test_the_default_is_unset_so_a_key_is_generated(self) -> None:
        """Read the declared default: the environment may override it in tests."""
        assert Settings.model_fields["secret_key"].default == INSECURE_DEFAULT_SECRET

    def test_validate_runtime_installs_a_usable_key(self, tmp_path: Path) -> None:
        settings = Settings(secret_key="", secret_key_file=tmp_path / "secret_key")

        settings.validate_runtime()

        assert not settings.uses_insecure_secret
        assert settings.secret_key

    def test_validate_runtime_keeps_an_explicit_key(self, tmp_path: Path) -> None:
        settings = Settings(secret_key="explicit", secret_key_file=tmp_path / "secret_key")

        settings.validate_runtime()

        assert settings.secret_key == "explicit"
        assert not (tmp_path / "secret_key").exists()

    def test_same_site_none_requires_a_secure_cookie(self) -> None:
        with pytest.raises(ValueError, match="AUTH_COOKIE_SECURE"):
            Settings(auth_cookie_samesite="none", auth_cookie_secure=False)
