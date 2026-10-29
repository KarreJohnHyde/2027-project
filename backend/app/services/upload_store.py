"""Reads and writes of stored uploads, applying encryption at rest.

Every component that touches an uploaded file goes through this module:
`store()` when writing, `materialize()` for libraries that need a file path,
`stream()` for downloads. Decrypted copies live only for the duration of a
`materialize()` block, in UPLOAD_DIR/.work, which is purged at start-up.

With an object store configured (app.services.object_store), every stored object
is also kept there and an instance that lacks a local copy fetches it on first read.
"""

from __future__ import annotations

import contextlib
import os
from functools import lru_cache
from pathlib import Path
from typing import Iterator

from fastapi import HTTPException, status

from app import config
from app.services import object_store
from app.services.storage_crypto import (
    KeyRing,
    StorageCryptoError,
    encrypt_file,
    is_encrypted,
    iter_plaintext,
    load_keyring,
    plaintext_path,
    purge_work_dir,
)


class ManagedStorageDeletionError(ValueError):
    """Raised when a database path is not a deletable managed upload object."""


def work_dir() -> Path:
    return config.UPLOAD_DIR / ".work"


@lru_cache(maxsize=1)
def keyring() -> KeyRing:
    return load_keyring()


def reset() -> None:
    """Re-reads key configuration (tests and key rotation)."""
    keyring.cache_clear()


def mode() -> str:
    return os.getenv("MEDTWIN_STORAGE_ENCRYPTION", config.STORAGE_ENCRYPTION_MODE).strip().lower()


def encryption_active() -> bool:
    return mode() != "off" and keyring().enabled


def store(plain_temporary: Path, target: Path) -> None:
    """Moves a validated plaintext temporary file into storage, encrypting it when configured,
    and keeps the durable copy when an object store is configured."""
    if mode() == "required" and not keyring().enabled:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Storage encryption is required but no key is configured; the upload was not stored.")
    durable = object_store.configured()
    if durable and not encryption_active():
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail="Durable object storage holds encrypted uploads only; configure a storage key. The upload was not stored.")
    if encryption_active():
        encrypt_file(plain_temporary, target, keyring())
        plain_temporary.unlink(missing_ok=True)
    else:
        os.replace(plain_temporary, target)
    if durable:
        try:
            object_store.put(target)
        except object_store.ObjectStoreError as exc:
            target.unlink(missing_ok=True)
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=f"{exc} The upload was not stored.") from exc


def available(path: Path) -> bool:
    """Whether the stored object exists here, first fetching its durable copy when this
    instance lacks it. Only content-addressed objects directly in UPLOAD_DIR are fetched."""
    if path.exists():
        return True
    if not object_store.configured() or path.parent.resolve(strict=False) != config.UPLOAD_DIR.resolve(strict=False):
        return False
    try:
        return object_store.fetch(path)
    except object_store.ObjectStoreError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


@contextlib.contextmanager
def materialize(path: Path) -> Iterator[Path]:
    available(path)
    try:
        with plaintext_path(path, keyring(), work_dir()) as plain:
            yield plain
    except StorageCryptoError as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail=f"Stored file could not be decrypted: {exc}") from exc


def stream(path: Path) -> Iterator[bytes]:
    available(path)
    return iter_plaintext(path, keyring())


def startup_cleanup() -> int:
    return purge_work_dir(work_dir())


def readiness() -> dict:
    ring = keyring()
    required = mode() == "required"
    return {
        "ready": ring.enabled or not required,
        "mode": mode(),
        "encryption_active": encryption_active(),
        "active_key_id": ring.active_id.hex() if ring.active_id else None,
        "configured_keys": len(ring.keys),
        "database_encrypted": False,
        "note": "Uploads are encrypted with AES-256-GCM when a key is configured; the SQLite database is not encrypted (use an encrypted volume).",
    }


def stored_file_encrypted(path: Path) -> bool:
    return available(path) and is_encrypted(path)


def resolve_managed_file(path: Path, stored_filename: str) -> Path | None:
    """Resolve one upload object without allowing deletion outside ``UPLOAD_DIR``.

    Uploaded objects are content-addressed direct children of ``UPLOAD_DIR``.  A
    missing object is a valid result for idempotent erasure, but its recorded path
    must still point to the expected direct child.  Symlinks and directories are
    refused so a corrupted database row cannot turn case deletion into an
    arbitrary filesystem operation.
    """
    if not stored_filename or Path(stored_filename).name != stored_filename:
        raise ManagedStorageDeletionError("Stored filename is not a plain filename.")

    recorded = Path(path)
    try:
        upload_root = config.UPLOAD_DIR.resolve(strict=False)
        candidate = recorded.resolve(strict=False)
    except (OSError, RuntimeError) as exc:
        raise ManagedStorageDeletionError("Recorded upload object could not be resolved safely.") from exc
    if recorded.name != stored_filename or candidate.parent != upload_root:
        raise ManagedStorageDeletionError("Recorded object is outside the managed upload root.")
    if recorded.is_symlink():
        raise ManagedStorageDeletionError("Managed upload objects may not be symbolic links.")
    if not available(recorded):
        return None
    if not recorded.is_file():
        raise ManagedStorageDeletionError("Recorded upload object is not a regular file.")

    try:
        resolved = recorded.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise ManagedStorageDeletionError("Recorded upload object could not be resolved safely.") from exc
    if resolved.parent != upload_root:
        raise ManagedStorageDeletionError("Resolved object is outside the managed upload root.")
    return resolved


def delete_managed_file(path: Path, stored_filename: str) -> bool:
    """Delete one validated upload object; return ``False`` when already absent."""
    target = resolve_managed_file(path, stored_filename)
    if target is None:
        return False
    try:
        target.unlink()
    except OSError as exc:
        raise ManagedStorageDeletionError("Managed upload object could not be deleted.") from exc
    # Its cached masked text (app.services.derived_text) goes with it; the name starts with the hash.
    file_hash = stored_filename.split(".", 1)[0]
    for derived in (config.UPLOAD_DIR / ".derived").glob(f"{file_hash}-*.json"):
        derived.unlink(missing_ok=True)
    if object_store.configured():
        try:
            object_store.delete(stored_filename)
        except object_store.ObjectStoreError as exc:
            raise ManagedStorageDeletionError(str(exc)) from exc
    return True
