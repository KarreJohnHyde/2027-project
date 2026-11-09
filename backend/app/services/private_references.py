"""Owner-only reference packets, isolated from the shared case workspace.

Originals, page previews, OCR and case reports are encrypted outside the source
tree. These records never become training labels, clinician reviews or public
demo seeds. The local import command is the only writer.
"""
from __future__ import annotations

import io
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID, uuid4

from fastapi import HTTPException

from app.services.storage_crypto import (
    encrypt_stream, generate_key, is_encrypted, load_keyring, read_plaintext,
)


def root_dir() -> Path:
    configured = os.getenv("MEDTWIN_PRIVATE_REFERENCE_DIR")
    local = Path(os.getenv("LOCALAPPDATA", Path.home() / ".local" / "share"))
    return Path(configured) if configured else local / "MedTwin" / "private-references"


def key_file() -> Path:
    return Path(os.getenv("MEDTWIN_PRIVATE_REFERENCE_KEY_FILE", str(root_dir().parent / "private-reference.key")))


def ring(*, create: bool = False):
    path = key_file()
    if create and not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump({"active": "local-1", "keys": {"local-1": generate_key()}}, handle)
    return load_keyring({"MEDTWIN_STORAGE_KEY_FILE": str(path)})


def binding(user) -> dict:
    return {"id": user.id, "username": user.username, "created_at": user.created_at.isoformat()}


def packet_dir(user, study_id: str) -> Path:
    try:
        if str(UUID(study_id)) != study_id:
            raise ValueError
    except ValueError:
        raise HTTPException(404, "Reference case not found.") from None
    root = root_dir().resolve()
    owner = root / str(int(user.id))
    target = owner / study_id
    if owner.is_symlink() or target.is_symlink() or target.resolve().parent != owner or owner.parent != root:
        raise HTTPException(404, "Reference case not found.")
    return target


def seal(path: Path, content: bytes, keys) -> None:
    # Write ciphertext only, atomically. No decrypted temporary report is made.
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.part")
    try:
        with temporary.open("xb") as handle:
            encrypt_stream(io.BytesIO(content), handle, len(content), keys)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load(user, study_id: str) -> dict:
    path = packet_dir(user, study_id) / "report.enc"
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Reference case not found.")
    try:
        if not is_encrypted(path):
            raise ValueError("Unencrypted private report refused")
        payload = json.loads(read_plaintext(path, ring()))
        if payload.get("owner") != binding(user) or payload.get("id") != study_id:
            raise HTTPException(404, "Reference case not found.")
        return payload
    except HTTPException:
        raise
    except Exception:
        # Do not expose disk paths, source text or crypto internals in errors/logs.
        raise HTTPException(503, "Private reference storage is unavailable or failed integrity verification.") from None


def public_report(payload: dict) -> dict:
    return {key: value for key, value in payload.items() if key not in {"owner", "assets", "import_key"}}


def listing(user) -> list[dict]:
    folder = root_dir().resolve() / str(int(user.id))
    if not folder.is_dir() or folder.is_symlink():
        return []
    result = []
    for path in sorted(folder.iterdir()):
        if not path.is_dir() or path.is_symlink():
            continue
        try:
            data = load(user, path.name)
        except HTTPException as error:
            if error.status_code == 404:
                continue
            raise
        result.append({key: data[key] for key in ("id", "title", "summary", "source_count", "page_count", "created_at", "trust")})
    return sorted(result, key=lambda item: item["created_at"])


def asset(user, study_id: str, asset_id: str) -> tuple[bytes, str]:
    payload = load(user, study_id)
    if not re.fullmatch(r"[a-zA-Z0-9_-]{1,80}", asset_id) or asset_id not in payload["assets"]:
        raise HTTPException(404, "Source not found.")
    path = packet_dir(user, study_id) / f"{asset_id}.enc"
    if not path.is_file() or path.is_symlink():
        raise HTTPException(404, "Source not found.")
    try:
        if not is_encrypted(path):
            raise ValueError
        content = read_plaintext(path, ring())
    except Exception:
        raise HTTPException(503, "Private source failed integrity verification.") from None
    return content, payload["assets"][asset_id]


def erase(user, study_id: str) -> None:
    load(user, study_id)  # authenticate ownership and envelope before any removal
    target = packet_dir(user, study_id).resolve()
    expected_parent = root_dir().resolve() / str(int(user.id))
    if target.parent != expected_parent or expected_parent.parent != root_dir().resolve():
        raise HTTPException(409, "Private storage path failed verification.")
    shutil.rmtree(target)


def import_packet(user, definition: dict) -> str:
    """Import a local, source-linked report definition, producing real local OCR.

    Re-importing an identical import_key is refused; existing reports are never
    overwritten. Corrections can be imported under a new revision key.
    """
    import hashlib
    from dataclasses import asdict
    from importlib.metadata import version
    import pypdfium2
    from PIL import Image
    from app.services.ocr import ocr_image, engine_version

    if not user.is_active or user.is_guest:
        raise ValueError("An active non-guest owner is required.")
    if not definition.get("import_key") or not definition.get("sources"):
        raise ValueError("import_key and sources are required.")
    if any(row.get("status") not in {"ABSTAIN", "NOT_RUN", "UNAVAILABLE"} for row in definition.get("model_outputs", [])):
        raise ValueError("Reference import cannot manufacture completed model predictions.")
    from urllib.parse import urlparse
    if any(urlparse(link.get("url", "")).scheme != "https" or not urlparse(link.get("url", "")).netloc
           for insight in definition.get("insights", []) for link in insight.get("links", [])):
        raise ValueError("Reference explanation links must use absolute HTTPS URLs.")
    for item in listing(user):
        if load(user, item["id"]).get("import_key") == definition["import_key"]:
            raise ValueError("This import revision already exists; nothing was overwritten.")
    source_ids = [source["id"] for source in definition["sources"]]
    if len(set(source_ids)) != len(source_ids) or any(not re.fullmatch(r"doc[0-9]+", s) for s in source_ids):
        raise ValueError("Sources require unique doc<number> identifiers.")
    for section in ("facts", "measurements", "timeline", "insights"):
        for row in definition.get(section, []):
            if not row.get("refs") or any(ref.get("source") not in source_ids or not isinstance(ref.get("page"), int) or ref["page"] < 1 for ref in row["refs"]):
                raise ValueError(f"Every {section} entry requires valid source-page references.")
    study_id = str(uuid4())
    folder = packet_dir(user, study_id)
    keys = ring(create=True)
    folder.mkdir(parents=True, exist_ok=False, mode=0o700)
    payload = {key: definition.get(key, []) for key in ("facts", "measurements", "timeline", "insights", "limitations", "conflicts", "model_outputs")}
    payload.update({"id": study_id, "owner": binding(user), "import_key": definition["import_key"],
                    "title": definition["title"], "summary": definition["summary"], "created_at": datetime.now(timezone.utc).isoformat(),
                    "trust": {"source": "USER_SUPPLIED", "integrity": "SHA256_VERIFIED", "extraction": "SOURCE_LINKED_REQUIRES_REVIEW",
                              "clinical_review": "NOT_REVIEWED", "ground_truth": False, "training_eligible": False},
                    "processing": {"ocr_engine": engine_version(), "renderer": f"pypdfium2 {version('pypdfium2')}",
                                   "summary_method": "Assisted transcription checked against selected source pages; not a diagnostic model.",
                                   "diagnostic_models_run": [], "forecast_status": "UNAVAILABLE"},
                    "sources": [], "assets": {}, "source_count": len(source_ids), "page_count": 0})
    try:
        for source in definition["sources"]:
            path = Path(source["path"])
            content = path.read_bytes()
            mime = "application/pdf" if path.suffix.lower() == ".pdf" else "image/jpeg"
            if path.suffix.lower() not in {".pdf", ".jpeg", ".jpg", ".png"}:
                raise ValueError("Only PDF and raster source images are supported.")
            if path.suffix.lower() == ".png":
                mime = "image/png"
            original_id = f"{source['id']}_original"
            seal(folder / f"{original_id}.enc", content, keys)
            payload["assets"][original_id] = mime
            document = pypdfium2.PdfDocument(content) if mime == "application/pdf" else None
            count = len(document) if document is not None else 1
            record = {"id": source["id"], "label": source["label"], "sha256": hashlib.sha256(content).hexdigest(),
                      "bytes": len(content), "original_asset": original_id, "pages": [], "page_count": count,
                      "contains_identifiers": True}
            try:
                for index in range(count):
                    if document is not None:
                        page = document[index]
                        bitmap = page.render(scale=2.0)
                        image = bitmap.to_pil().copy()
                        bitmap.close()
                        page.close()
                    else:
                        image = Image.open(io.BytesIO(content)).convert("RGB")
                    result = asdict(ocr_image(image))
                    buffer = io.BytesIO()
                    image.save(buffer, format="PNG")
                    image.close()
                    page_id = f"{source['id']}_page_{index + 1}"
                    seal(folder / f"{page_id}.enc", buffer.getvalue(), keys)
                    payload["assets"][page_id] = "image/png"
                    record["pages"].append({"page": index + 1, "asset": page_id, "ocr": result,
                                            "description": source.get("pages", {}).get(str(index + 1), "Source page; interpretation pending review.")})
            finally:
                if document is not None:
                    document.close()
            payload["sources"].append(record)
            payload["page_count"] += count
        counts = {source["id"]: source["page_count"] for source in payload["sources"]}
        for section in ("facts", "measurements", "timeline", "insights"):
            if any(ref["page"] > counts[ref["source"]] for row in payload[section] for ref in row["refs"]):
                raise ValueError("A report reference points beyond its source document.")
        seal(folder / "report.enc", json.dumps(payload, ensure_ascii=False).encode(), keys)
        # Verify every encrypted object and all original byte hashes before success.
        verified = load(user, study_id)
        for asset_id in verified["assets"]:
            asset(user, study_id, asset_id)  # authenticate every encrypted preview and original
        for source in verified["sources"]:
            original, _ = asset(user, study_id, source["original_asset"])
            if hashlib.sha256(original).hexdigest() != source["sha256"]:
                raise ValueError("Original source failed byte-integrity verification.")
        return study_id
    except BaseException:
        if folder.resolve().parent == root_dir().resolve() / str(int(user.id)):
            shutil.rmtree(folder)
        raise
