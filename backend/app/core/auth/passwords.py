"""Password hashing.

argon2id via pwdlib. Passwords are never stored or logged in plain text
(docs/architecture.md, section 44).
"""

from __future__ import annotations

from pwdlib import PasswordHash

_hasher = PasswordHash.recommended()


def hash_password(plain: str) -> str:
    return _hasher.hash(plain)


def verify_password(plain: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(plain, password_hash)
    except Exception:
        return False


def rehash_if_needed(plain: str, password_hash: str) -> str:
    """Return a hash upgraded to current parameters, or the original one."""
    _, updated = _hasher.verify_and_update(plain, password_hash)
    return updated or password_hash
