"""Stable local development signing keys; production still requires SECRET_KEY."""
from __future__ import annotations

import os
from pathlib import Path
import secrets
import time


def resolve_signing_key(configured: str, environment: str, local_path: Path) -> str:
    if environment in {"production", "staging"} and len(configured) < 32:
        raise RuntimeError("SECRET_KEY must contain at least 32 characters outside development/test environments.")
    if configured:
        return configured
    if environment != "development":
        return secrets.token_urlsafe(48)
    local_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(local_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Concurrent API/worker startup can overlap the first write. Never
        # replace a persisted key and invalidate existing workspace sessions.
        for _ in range(20):
            value = local_path.read_text(encoding="ascii").strip()
            if value:
                if 32 <= len(value) <= 4096:
                    return value
                raise RuntimeError("Local signing key is invalid; configure SECRET_KEY or restore the key file.")
            time.sleep(.05)
        raise RuntimeError("Local signing key is empty; configure SECRET_KEY or restore the key file.")
    else:
        value = secrets.token_urlsafe(48)
        with os.fdopen(fd, "w", encoding="ascii") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        return value
