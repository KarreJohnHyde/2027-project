"""Durable copies of stored uploads in object storage (Vercel Blob, private store).

A serverless instance keeps files only in its own temporary directory, so an upload stored by
one instance is missing on the next. When an object store is configured, every upload object
is also written to it as ``uploads/<stored file name>`` (already encrypted: upload_store
refuses durable storage without encryption at rest), and an instance without a local copy
fetches it before reading. Upload objects are content-addressed, so a name always denotes the
same plaintext.

Configured by BLOB_READ_WRITE_TOKEN, or on Vercel by the project's connected Blob store
(BLOB_STORE_ID with the deployment's OIDC token); MEDTWIN_OBJECT_STORE=off disables it.
"""

from __future__ import annotations

import os
from pathlib import Path

PREFIX = "uploads/"


class ObjectStoreError(RuntimeError):
    """The object store could not complete an operation (the message names no content)."""


def configured() -> bool:
    if os.getenv("MEDTWIN_OBJECT_STORE", "auto").strip().lower() == "off":
        return False
    return bool(os.getenv("BLOB_READ_WRITE_TOKEN", "").strip() or os.getenv("BLOB_STORE_ID", "").strip())


def _client():
    # vercel-blob is installed for the Vercel deployment only (backend/pyproject.toml).
    from vercel.blob import sync as blob

    return blob


def put(path: Path) -> None:
    """Write the stored object at ``path`` under its own name, replacing an earlier copy."""
    try:
        with path.open("rb") as handle:
            _client().put_blob(PREFIX + path.name, handle, access="private", content_length=path.stat().st_size,
                               content_type="application/octet-stream", allow_overwrite=True)
    except Exception as exc:
        raise ObjectStoreError(f"Upload object could not be stored durably ({type(exc).__name__}).") from exc


def fetch(path: Path) -> bool:
    """Write the durable copy of ``path`` there; False when the store has no such object."""
    client = _client()
    try:
        result = client.get_blob(PREFIX + path.name, access="private")
    except client.BlobNotFoundError:
        return False
    except Exception as exc:
        raise ObjectStoreError(f"Upload object could not be read from durable storage ({type(exc).__name__}).") from exc
    partial = path.with_name(f".fetch-{path.name}.part")
    partial.write_bytes(result.body)
    os.replace(partial, path)
    return True


def delete(name: str) -> None:
    try:
        _client().delete_blob(PREFIX + name)
    except Exception as exc:
        raise ObjectStoreError(f"Upload object could not be deleted from durable storage ({type(exc).__name__}).") from exc
