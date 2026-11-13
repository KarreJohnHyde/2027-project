"""Authorized, bounded opt-in word ROI proposals from canonical masked previews."""
from __future__ import annotations
import hashlib
import io
import json
import threading
import math
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import User
from app.routers.modalities import _report_upload, get_report_page_image, PAGE_IMAGE_DPI
from app.security import rate_limit
from app.services.auth import get_current_user
from app.services.audit_service import log_audit_event
from app.services import upright_word_ocr as service
from app.services import derived_text, upload_store, ocr

router = APIRouter(tags=["Upright single-word OCR research"])
_work_lock = threading.Lock()


class UprightWordRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page: int = Field(default=1, ge=1, le=500)
    bbox_xyxy: list[int] = Field(min_length=4, max_length=4)
    expected_image_size: list[int] = Field(min_length=2, max_length=2)
    source_file_sha256: str = Field(pattern="^[a-f0-9]{64}$")
    coordinate_space: Literal["REPORT_PAGE_PREVIEW_110_DPI"]
    upright_attested: bool = False
    single_word_attested: bool = False
    latin_text_attested: bool = False


@router.get("/universal/ocr/upright-word/capability")
def capability(current_user: User = Depends(get_current_user)):
    return service.capability()


@router.post("/uploads/{file_id}/ocr/upright-word", dependencies=[Depends(rate_limit("upright-word-ocr", 10))])
def recognise_word(file_id: int, request: UprightWordRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = _report_upload(file_id, db, current_user)
    if not record.filename.lower().endswith(".pdf"):
        return service.refusal("PDF_REPORT_PREVIEW_REQUIRED", "This contract accepts only canonical privacy-masked PDF report previews.")
    if record.file_hash != request.source_file_sha256:
        raise HTTPException(409, detail="The source file identity differs from the selected upload; refresh the source preview.")
    if PAGE_IMAGE_DPI != 110:
        return service.refusal("PREVIEW_RENDER_CONTRACT_CHANGED", "The preview rendering profile differs from the evaluated coordinate contract.")
    source = {"upload_id": record.id, "case_id": record.case_id, "file_sha256": record.file_hash, "page": request.page,
              "coordinate_space": request.coordinate_space, "preview_dpi": 110}
    early = service.validate_roi(request.expected_image_size, request.bbox_xyxy, upright_attested=request.upright_attested,
                                 single_word_attested=request.single_word_attested, latin_text_attested=request.latin_text_attested)
    if early: return service.refusal(early, "The source selection/attestation is outside the bounded word-ROI contract.", source)
    if not _work_lock.acquire(blocking=False): raise HTTPException(429, detail="Word OCR is already processing a source; retry after it finishes.")
    try:
        prepared = derived_text.load(record.file_hash)
        if prepared is None:
            return service.refusal("OCR_SOURCE_CONTEXT_NOT_READY", "Run the existing report analysis/source verification first; this crop endpoint does not initiate whole-document OCR.", source)
        pages = prepared[2]
        if not 1 <= request.page <= len(pages): raise HTTPException(404, detail="Page not found.")
        metadata = pages[request.page - 1]
        if metadata.get("method") != "OCR" or not metadata.get("image_width") or not metadata.get("image_height"):
            return service.refusal("SOURCE_PAGE_PRIVACY_MASKING_UNAVAILABLE", "OCR-backed source geometry/identifier-masking metadata is required; use the existing embedded source text/reviewer controls.", source)
        if record.file_size_bytes > 50 * 1024 * 1024:
            return service.refusal("SOURCE_RESOURCE_BOUND_EXCEEDED", "The source exceeds the bounded interactive crop contract.", source)
        # Check PDF page size before calling the existing preview renderer.
        # Merely inspecting page geometry never exposes unmasked image/text.
        import pypdfium2
        with upload_store.materialize(Path(record.file_path)) as plain, ocr.PDFIUM_LOCK:
            document = pypdfium2.PdfDocument(str(plain))
            try:
                if request.page > len(document): raise HTTPException(404, detail="Page not found.")
                page = document[request.page - 1]
                try: width_pt, height_pt = page.get_size()
                finally: page.close()
            finally: document.close()
        if math.ceil(width_pt * 110 / 72) * math.ceil(height_pt * 110 / 72) > service.BOUNDS["max_source_pixels"]:
            return service.refusal("SOURCE_RENDER_BOUND_EXCEEDED", "The selected PDF page exceeds the interactive preview-pixel budget.", source)
        # Reuse the exact authorized privacy-masked110DPI preview displayed by
        # source verification; never reopen an unmasked image behind that view.
        response = get_report_page_image(file_id, request.page, db, current_user)
        header = json.loads(response.headers["X-MedTwin-Page"])
        source.update(preview_sha256=hashlib.sha256(response.body).hexdigest(), privacy_masking=header["masking"])
        if header["masking"] == "UNAVAILABLE_EMBEDDED_TEXT":
            return service.refusal("SOURCE_PAGE_PRIVACY_MASKING_UNAVAILABLE", "Use existing embedded source text/reviewer controls; OCR-backed identifier masking metadata is required for this opt-in crop path.", source)
        with Image.open(io.BytesIO(response.body)) as decoded:
            if list(decoded.size) != request.expected_image_size:
                raise HTTPException(409, detail="The displayed source dimensions differ; refresh the canonical page preview before choosing a crop.")
            image = decoded.convert("RGB")
        result = service.recognise(image, request.bbox_xyxy, source=source, upright_attested=request.upright_attested,
                                   single_word_attested=request.single_word_attested, latin_text_attested=request.latin_text_attested)
        log_audit_event(db=db, action="UPRIGHT_WORD_OCR_PROPOSAL", resource_type="FILE", resource_id=str(file_id), user=current_user,
                        details={"case_id": record.case_id, "page": request.page, "bbox_xyxy": request.bbox_xyxy,
                                 "source_sha256": record.file_hash, "preview_sha256": source["preview_sha256"],
                                 "status": result["status"], "code": result["code"], "clinical_activation": False})
        return result
    except HTTPException: raise
    except (OSError, ValueError, KeyError, RuntimeError) as exc:
        return service.refusal("SOURCE_OR_OCR_UNAVAILABLE", "The canonical source/engine could not provide a trustworthy word proposal; use the original review workflow.", source, status="ABSTAIN")
    finally:
        _work_lock.release()
