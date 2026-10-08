"""Where the bytes live, behind one interface.

`docs/architecture.md` section 43 asks for exactly this: the first implementation
may be a local volume, S3 / MinIO / a cloud bucket may follow, and every one of
them hides behind a single `FileService` so that modules never touch a filesystem
or a client library.

`FileStorage` is that second seam, below the service. Keeping it separate from
`FileService` is what makes the answer to "is S3 worth making a module?" yes:
the module implements this one protocol, registers itself, and nothing above it
changes. The service owns *policy* - who may store what, how much of it - and the
storage owns *bytes*.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

from app.core.errors import NotFoundError


@runtime_checkable
class FileStorage(Protocol):
    """Bytes in, bytes out. No paths cross this boundary."""

    async def save(self, key: str, data: bytes) -> None:
        """Store `data` under `key`, replacing anything already there."""

    async def read(self, key: str) -> bytes:
        """The bytes stored under `key`; raises when there are none."""

    async def delete(self, key: str) -> None:
        """Remove `key`. Deleting what is not there is not an error."""

    async def exists(self, key: str) -> bool:
        """Whether `key` currently holds anything."""


class LocalVolumeStorage:
    """Files on a mounted volume.

    Keys are opaque strings and nothing else may build one: the service generates
    them, and this class joins them onto its root without inspecting them. The
    two-level fan-out (`<org>/<xx>/<rest>`) is not tidiness - a single directory
    with a hundred thousand entries in it is slow to list and slower to back up,
    and the department a file belongs to is not knowable from a key alone.
    """

    def __init__(self, root: Path) -> None:
        self._root = root

    def _path(self, key: str) -> Path:
        # `Path` would collapse a `..` in the key, and a key is not trusted
        # input - it is simply never allowed to point outside the root.
        if not key or key.startswith("/") or ".." in key.split("/"):
            raise NotFoundError("Invalid storage key")
        return self._root / key

    async def save(self, key: str, data: bytes) -> None:
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        # Write beside the target and move it into place, so a reader never sees a
        # half-written file under its final name.
        temporary = path.with_suffix(".part")
        temporary.write_bytes(data)
        temporary.replace(path)

    async def read(self, key: str) -> bytes:
        path = self._path(key)
        if not path.exists():
            raise NotFoundError("File is missing from storage")
        return path.read_bytes()

    async def delete(self, key: str) -> None:
        path = self._path(key)
        path.unlink(missing_ok=True)

    async def exists(self, key: str) -> bool:
        return self._path(key).exists()


def build_storage(root: Path) -> FileStorage:
    """The implementation the installation runs.

    Chosen from settings rather than hardcoded so that the S3 module has a place
    to plug in: with more than one implementation registered, this returns the one
    the module registry says is active instead of this one.
    """
    return LocalVolumeStorage(root)
