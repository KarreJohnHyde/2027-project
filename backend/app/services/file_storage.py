"""
Controlled server-side file store with security hardening:
- Path traversal prevention
- MIME type, extension and content-signature validation
- Per-modality payload size bounds, streamed to disk while hashing
- SHA-256 cryptographic hashing for integrity & idempotency
- Modality detection & association enforcement
"""

import hashlib
import json
import os
import re
import secrets
from pathlib import Path
from typing import Tuple
from fastapi import HTTPException, UploadFile, status

from app.config import UPLOAD_DIR, MAX_UPLOAD_SIZE_BYTES, MAX_IMAGE_UPLOAD_SIZE_BYTES, ALLOWED_EXTENSIONS, ALLOWED_MIME_TYPES
from app.services import upload_store
from app.models.entities import ModalityType

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg", ".bmp", ".dcm", ".nii", ".nii.gz", ".nrrd", ".mha")
ECG_EXTENSIONS = (".csv", ".dat", ".hea")
REPORT_EXTENSIONS = (".txt", ".json", ".pdf", ".docx", ".md", ".xlsx")

EXPECTED_MIME_TYPES = {
    ".png": {"image/png", "application/octet-stream"},
    ".jpg": {"image/jpeg", "application/octet-stream"},
    ".jpeg": {"image/jpeg", "application/octet-stream"},
    ".bmp": {"image/bmp", "image/x-ms-bmp", "application/octet-stream"},
    ".dcm": {"application/dicom", "application/octet-stream"},
    ".nii": {"application/octet-stream"},
    ".nii.gz": {"application/gzip", "application/x-gzip", "application/octet-stream"},
    ".nrrd": {"application/octet-stream"},
    ".mha": {"application/octet-stream"},
    ".csv": {"text/csv", "text/plain", "application/octet-stream"},
    ".txt": {"text/plain", "application/octet-stream"},
    ".md": {"text/markdown", "text/plain", "application/octet-stream"},
    ".json": {"application/json", "application/fhir+json", "text/plain", "application/octet-stream"},
    ".pdf": {"application/pdf", "application/octet-stream"},
    ".docx": {"application/vnd.openxmlformats-officedocument.wordprocessingml.document", "application/octet-stream"},
    ".xlsx": {"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "application/octet-stream"},
    ".dat": {"application/octet-stream", "text/plain"},
    ".hea": {"application/octet-stream", "text/plain"},
}


def ensure_upload_dir() -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    return UPLOAD_DIR


def sanitize_filename(filename: str) -> str:
    """Strip directory traversals and invalid characters."""
    clean_name = os.path.basename(filename.replace("\\", "/"))
    clean_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', clean_name)
    if not clean_name or clean_name.startswith('.'):
        clean_name = f"upload_{clean_name}"
    return clean_name


def extension_of(filename: str) -> str:
    lower = filename.lower()
    return ".nii.gz" if lower.endswith(".nii.gz") else Path(lower).suffix


def detect_modality(filename: str, mime_type: str) -> ModalityType:
    ext = extension_of(filename)
    if ext in IMAGE_EXTENSIONS:
        return ModalityType.IMAGE
    elif ext in ECG_EXTENSIONS:
        return ModalityType.ECG
    elif ext in REPORT_EXTENSIONS:
        return ModalityType.REPORT
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file format '{ext}'. Must be an image, digital ECG, or clinical report."
        )


def _looks_like_text(head: bytes) -> bool:
    if b"\x00" in head:
        return False
    try:
        head.decode("utf-8")
        return True
    except UnicodeDecodeError:
        # A truncated multi-byte character at the boundary is still text.
        try:
            head[:-3].decode("utf-8")
            return True
        except UnicodeDecodeError:
            return all(byte >= 0x09 for byte in head)


def validate_signature(ext: str, head: bytes) -> None:
    """Reject content whose leading bytes contradict the declared format."""
    checks = {
        ".png": head.startswith(b"\x89PNG\r\n\x1a\n"),
        ".jpg": head.startswith(b"\xff\xd8\xff"),
        ".jpeg": head.startswith(b"\xff\xd8\xff"),
        ".bmp": head.startswith(b"BM"),
        ".pdf": head.startswith(b"%PDF-"),
        ".docx": head.startswith(b"PK\x03\x04"),
        ".xlsx": head.startswith(b"PK\x03\x04"),
        ".dcm": len(head) >= 132 and head[128:132] == b"DICM",
        ".nii.gz": head.startswith(b"\x1f\x8b"),
        ".nii": len(head) >= 4 and (int.from_bytes(head[:4], "little") in (348, 540) or int.from_bytes(head[:4], "big") in (348, 540)),
        ".nrrd": head.startswith(b"NRRD000"),
        ".mha": b"ObjectType" in head[:1024] and b"ElementDataFile" in head,
    }
    if ext in checks and not checks[ext]:
        detail = {
            ".dcm": "DICOM uploads must be Part 10 files with the 128-byte preamble and 'DICM' prefix.",
        }.get(ext, f"File content does not match the declared '{ext}' format.")
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=detail)
    if ext in (".txt", ".md", ".csv", ".json", ".hea") and not _looks_like_text(head):
        raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail=f"'{ext}' uploads must be text.")


def validate_complete_content(ext: str, path: Path) -> None:
    if ext == ".json":
        try:
            json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise HTTPException(status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE, detail="JSON upload does not parse as UTF-8 JSON.")


async def save_uploaded_file(upload_file: UploadFile) -> Tuple[str, str, str, int, ModalityType]:
    """
    Validates, streams, hashes, and safely stores the uploaded file.
    Returns: (original_filename, stored_filename, file_hash, file_size, modality)
    """
    ensure_upload_dir()

    original_filename = sanitize_filename(upload_file.filename or "unnamed_file")
    ext = extension_of(original_filename)

    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File extension '{ext}' is not permitted. Allowed: {sorted(list(ALLOWED_EXTENSIONS))}"
        )

    mime_type = upload_file.content_type or "application/octet-stream"
    if mime_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"MIME type '{mime_type}' is not permitted for clinical evidence uploads.",
        )
    if mime_type not in EXPECTED_MIME_TYPES.get(ext, {mime_type}):
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail=f"MIME type '{mime_type}' does not match file extension '{ext}'.",
        )

    modality = detect_modality(original_filename, mime_type)
    limit = MAX_IMAGE_UPLOAD_SIZE_BYTES if modality == ModalityType.IMAGE else MAX_UPLOAD_SIZE_BYTES

    hasher = hashlib.sha256()
    total_bytes = 0
    head = b""
    temporary = UPLOAD_DIR / f".incoming-{secrets.token_hex(12)}.part"
    try:
        with open(temporary, "xb") as handle:
            while True:
                chunk = await upload_file.read(1024 * 1024)
                if not chunk:
                    break
                total_bytes += len(chunk)
                if total_bytes > limit:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"File exceeds the {limit // (1024 * 1024)} MB limit for {modality.value.lower()} uploads."
                    )
                if len(head) < 2048:
                    head += chunk[: 2048 - len(head)]
                hasher.update(chunk)
                handle.write(chunk)

        if total_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded file is empty (0 bytes). Invalid input."
            )
        validate_signature(ext, head)
        validate_complete_content(ext, temporary)

        file_hash = hasher.hexdigest()
        stored_filename = f"{file_hash}{ext}"
        target_path = UPLOAD_DIR / stored_filename

        # Content-addressed storage makes repeated uploads idempotent at rest as well
        # as in the database. Existing bytes with the same SHA-256 are not rewritten.
        # New content is encrypted at rest when a storage key is configured.
        if target_path.exists():
            temporary.unlink()
        else:
            upload_store.store(temporary, target_path)
    finally:
        if temporary.exists():
            temporary.unlink()

    return original_filename, stored_filename, file_hash, total_bytes, modality
