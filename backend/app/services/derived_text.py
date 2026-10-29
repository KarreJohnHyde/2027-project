"""Cached reading of a report upload: its masked page text and page metadata.

Reading a photographed packet takes seconds per page. The analysis reads a document once;
later views of its text, its page list and the verification screen read this cache instead of
running OCR again. The cache holds only what the API may show (masked text, page types, line
boxes without their text), is encrypted like the upload when a storage key is configured, is
keyed by the file's SHA-256 and a fingerprint of the reading code (so any change to OCR,
masking or page typing reads the document again), and is deleted with the stored upload. It
is a local cache: an instance without it reads the document again.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from app import config
from app.services import upload_store
from app.services.storage_crypto import StorageCryptoError, encrypt_file, read_plaintext

Prepared = tuple[str, list[int], list[dict[str, Any]]]
SHA256_HEX = re.compile(r"[0-9a-f]{64}")


def cache_dir() -> Path:
    return config.UPLOAD_DIR / ".derived"


@lru_cache(maxsize=1)
def fingerprint() -> str:
    """Changes whenever the code that reads, masks or types pages changes."""
    from app.services import document_parser, nlp_processor, ocr, ocr_text, page_classifier

    digest = hashlib.sha256()
    for module in (document_parser, nlp_processor, ocr, ocr_text, page_classifier):
        digest.update(Path(module.__file__).read_bytes())
    digest.update(str(ocr.engine_version()).encode("utf-8"))
    return digest.hexdigest()[:16]


def _path(file_hash: str) -> Optional[Path]:
    return cache_dir() / f"{file_hash}-{fingerprint()}.json" if SHA256_HEX.fullmatch(file_hash or "") else None


def load(file_hash: str) -> Optional[Prepared]:
    path = _path(file_hash)
    if path is None or not path.exists():
        return None
    try:
        data = json.loads(read_plaintext(path, upload_store.keyring()))
        return data["text"], data["page_starts"], data["pages"]
    except (StorageCryptoError, ValueError, KeyError, OSError):
        path.unlink(missing_ok=True)  # unreadable (key rotated away, truncated): read the document again
        return None


def save(file_hash: str, prepared: Prepared) -> None:
    path = _path(file_hash)
    # Without a key under "required" encryption nothing derived from an upload is written in clear.
    if path is None or (upload_store.mode() == "required" and not upload_store.encryption_active()):
        return
    text, starts, pages = prepared
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False, suffix=".tmp") as handle:
        handle.write(json.dumps({"text": text, "page_starts": starts, "pages": pages}).encode("utf-8"))
    temporary = Path(handle.name)
    try:
        if upload_store.encryption_active():
            encrypt_file(temporary, path, upload_store.keyring())
        else:
            os.replace(temporary, path)
    except OSError:
        pass  # a failed cache write only costs reading the document again
    finally:
        temporary.unlink(missing_ok=True)


def delete(file_hash: str) -> int:
    """Removes every cached reading of one file (all code versions)."""
    if not SHA256_HEX.fullmatch(file_hash or "") or not cache_dir().exists():
        return 0
    removed = 0
    for path in cache_dir().glob(f"{file_hash}-*.json"):
        path.unlink(missing_ok=True)
        removed += 1
    return removed


def prepared(report_path: Path, file_hash: Optional[str]) -> Prepared:
    """The masked page text of a report, from the cache when this code has read it before."""
    from app.services.nlp_processor import prepare_report_document

    cached = load(file_hash) if file_hash else None
    if cached is not None:
        return cached
    result = prepare_report_document(report_path)
    if file_hash:
        save(file_hash, result)
    return result
