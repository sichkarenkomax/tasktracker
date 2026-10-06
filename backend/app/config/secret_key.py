"""Resolution of the JWT signing key.

A self-hosted instance must not require the operator to run a Python one-liner
before the very first ``docker compose up``, yet it also must never sign tokens
with a value that is published in the repository. Both are satisfied by
generating the key once, storing it on a mounted volume and reusing it on every
later start.

Precedence:

1. ``SECRET_KEY`` in the environment - explicit wins, e.g. to share one key
   across several instances or to keep it in a secret manager;
2. the file at ``SECRET_KEY_FILE``;
3. a freshly generated key, written to that file.

Losing the file means losing every session, so the caller is warned loudly
enough to be noticed in the logs.
"""

from __future__ import annotations

import logging
import os
import secrets
from pathlib import Path

from app.config.settings import INSECURE_DEFAULT_SECRET

logger = logging.getLogger(__name__)

#: 48 bytes of entropy, encoded as URL-safe text.
GENERATED_KEY_BYTES = 48

#: Read-only for the owner; the app never runs as root.
_FILE_MODE = 0o600


def load_or_create_secret_key(*, secret_key: str, secret_key_file: Path) -> tuple[str, Path | None]:
    """Return the signing key to use and the file it was read from or written to."""
    if secret_key and secret_key != INSECURE_DEFAULT_SECRET:
        return secret_key, None

    try:
        existing = secret_key_file.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        existing = ""
    except OSError as exc:
        raise RuntimeError(
            f"Cannot read the signing key from {secret_key_file}: {exc}. Either fix the "
            "permissions or set SECRET_KEY explicitly."
        ) from exc

    if existing:
        logger.info("secret_key.loaded_from_file path=%s", secret_key_file)
        return existing, secret_key_file

    generated = secrets.token_urlsafe(GENERATED_KEY_BYTES)
    try:
        secret_key_file.parent.mkdir(parents=True, exist_ok=True)
        secret_key_file.write_text(generated, encoding="utf-8")
        os.chmod(secret_key_file, _FILE_MODE)
    except OSError as exc:
        raise RuntimeError(
            f"Cannot store the generated signing key in {secret_key_file}: {exc}. Mount a "
            "writable volume there or set SECRET_KEY explicitly."
        ) from exc

    logger.warning(
        "secret_key.generated path=%s - back this file up, deleting it invalidates every "
        "session. Set SECRET_KEY in the environment to manage the key yourself.",
        secret_key_file,
    )
    return generated, secret_key_file
