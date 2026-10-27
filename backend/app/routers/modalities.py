"""Modality registry, imaging metadata/rendering, and parsed report text."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal, Optional

from contextlib import ExitStack

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import ModalityType, UploadedFile, User
from app.services import upload_store
from app.services.auth import get_current_user, verify_case_access
from app.services.dicom_series import assemble_series
from app.services.imaging_readers import ImagingReadError, read_metadata, render_slice
from app.services.modality_registry import modality_registry
from app.services.nlp_processor import EXTRACTOR_VERSION, prepare_report_document

router = APIRouter(tags=["Modalities & Imaging"])


@router.get("/modalities")
def get_modality_registry(current_user: User = Depends(get_current_user)):
    return modality_registry()


def _upload(file_id: int, db: Session, user: User) -> UploadedFile:
    record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(record.case_id, user, db, access="read")
    return record


@router.get("/uploads/{file_id}/imaging/metadata")
def get_imaging_metadata(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = _upload(file_id, db, current_user)
    if record.modality != ModalityType.IMAGE:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNSUPPORTED_MODALITY: not an imaging upload.")
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            metadata = read_metadata(plain)
    except ImagingReadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return {
        "upload_id": record.id,
        "filename": record.filename,
        "sha256": record.file_hash,
        **metadata,
        "inference": {"status": "MODEL_NOT_VALIDATED", "detections": [], "segmentations": [], "reason": "No validated imaging model is configured; no overlay is produced."},
    }


class DicomSeriesRequest(BaseModel):
    upload_ids: list[int] = Field(..., min_length=2, max_length=2000)
    series_reference: Optional[str] = Field(default=None, pattern="^[0-9a-f]{16}$")

    model_config = ConfigDict(extra="forbid")


@router.post("/cases/{case_id}/dicom-series/assemble")
def assemble_case_dicom_series(case_id: int, request: DicomSeriesRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Validate and order a multi-file DICOM series from this case's uploads.

    Returns the geometry report (ordering, spacing, LPS affine, issues). Nothing is persisted and
    no model runs; a rejected series states every reason. Only associated, non-withdrawn DICOM
    uploads of the same case are accepted."""
    verify_case_access(case_id, current_user, db, access="read")
    ids = list(dict.fromkeys(request.upload_ids))
    records = db.query(UploadedFile).filter(UploadedFile.id.in_(ids), UploadedFile.case_id == case_id).all()
    found = {record.id: record for record in records}
    missing = [upload_id for upload_id in ids if upload_id not in found]
    if missing:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "UPLOADS_NOT_IN_CASE", "upload_ids": missing})
    unusable = [upload_id for upload_id in ids if not found[upload_id].is_associated or found[upload_id].withdrawn_at is not None]
    if unusable:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "UPLOADS_NOT_CASE_BOUND", "upload_ids": unusable})
    try:
        with ExitStack() as stack:
            paths = [stack.enter_context(upload_store.materialize(Path(found[upload_id].file_path))) for upload_id in ids]
            report = assemble_series(paths, request.series_reference)
    except Exception as exc:  # unreadable or non-DICOM input is a typed refusal, not a server error
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "NOT_A_READABLE_DICOM_SERIES", "error": type(exc).__name__})
    if "ordered_input_indices" in report:
        report["ordered_upload_ids"] = [ids[index] for index in report.pop("ordered_input_indices")]
    report["upload_ids"] = ids
    report["inference"] = {"status": "NOT_RUN", "reason": "Series assembly validates geometry only; no volumetric upload model is activated."}
    return report


@router.get("/uploads/{file_id}/imaging/render")
def render_imaging_slice(
    file_id: int,
    index: Optional[int] = Query(None, ge=0),
    axis: Literal["axial", "coronal", "sagittal"] = "axial",
    center: Optional[float] = None,
    width: Optional[float] = Query(None, gt=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """One display slice as PNG; the source mapping is returned in X-MedTwin-Render."""
    record = _upload(file_id, db, current_user)
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            png, info = render_slice(plain, index=index, axis=axis, center=center, width=width)
    except ImagingReadError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    return Response(
        content=png,
        media_type="image/png",
        headers={"X-MedTwin-Render": json.dumps(info, separators=(",", ":")), "Cache-Control": "private, max-age=300"},
    )


@router.get("/uploads/{file_id}/text")
def get_parsed_report_text(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """The de-identified text the extractor read, so source spans can be shown in context."""
    record = _upload(file_id, db, current_user)
    if record.modality != ModalityType.REPORT:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNSUPPORTED_MODALITY: not a report upload.")
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            text, page_starts, page_meta = prepare_report_document(plain)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Report could not be parsed: {exc}")
    return {
        "upload_id": record.id,
        "filename": record.filename,
        "source_sha256": record.file_hash,
        "text": text,
        "text_sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
        "page_starts": page_starts,
        "pages": page_meta,
        "extractor_version": EXTRACTOR_VERSION,
        "deidentification_applied": True,
    }
