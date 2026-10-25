"""
File Upload, Storage, and Retrieval Router for MedTwin.
Enforces case association, MIME type validation, SHA-256 idempotency, and path traversal defense.
"""

from pathlib import Path
from typing import List, Optional
from urllib.parse import quote
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_UPLOAD_PER_MINUTE, UPLOAD_DIR
from app.database import get_db
from app.security import rate_limit
from app.models.entities import UploadedFile, User, Examination
from app.schemas.entities import FileUploadResponse
from app.services.auth import get_current_user, verify_case_access
from app.services import upload_store
from app.services.file_storage import save_uploaded_file
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["File Ingestion"])


def _form_bool(value: Optional[str], default: bool) -> bool:
    if value is None or value.strip() == "":
        return default
    text = value.strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"Expected a boolean, got {value!r}.")


@router.post(
    "/cases/{case_id}/uploads",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", RATE_LIMIT_UPLOAD_PER_MINUTE))],
)
async def upload_case_file(
    case_id: int,
    file: UploadFile = File(...),
    examination_id: Optional[int] = Form(None),
    # A string so an omitted field keeps the documented default (associated): FastAPI
    # 0.159 reads any missing boolean form field as False, like an unchecked checkbox.
    is_associated: Optional[str] = Form(None),
    association_notes: Optional[str] = Form(None),
    deidentified: bool = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Ingests and securely binds a digital medical record to an authorized case.
    Enforces idempotency: If the same file (identical SHA-256) is uploaded again to the case,
    returns the existing record rather than duplicating work.
    """
    case = verify_case_access(case_id, current_user, db)
    is_associated = _form_bool(is_associated, default=True)

    if not deidentified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload rejected: de-identified research-data attestation is required.",
        )

    if examination_id:
        exam = db.query(Examination).filter(
            Examination.id == examination_id,
            Examination.case_id == case_id
        ).first()
        if not exam:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Examination ID {examination_id} does not belong to case {case_id}."
            )

    # Save and hash file
    orig_name, stored_name, file_hash, file_size, modality = await save_uploaded_file(file)

    # Idempotency check: see if file hash already stored for this case
    existing_file = db.query(UploadedFile).filter(
        UploadedFile.case_id == case_id,
        UploadedFile.file_hash == file_hash
    ).first()
    if existing_file:
        log_audit_event(
            db=db,
            action="FILE_UPLOAD_IDEMPOTENT_HIT",
            resource_type="FILE",
            resource_id=str(existing_file.id),
            user=current_user,
            details={
                "case_id": case_id,
                "file_hash": file_hash,
                "deidentified_attested": True,
            }
        )
        return existing_file

    db_file = UploadedFile(
        case_id=case.id,
        examination_id=examination_id,
        filename=orig_name,
        stored_filename=stored_name,
        file_path=str(UPLOAD_DIR / stored_name),
        file_hash=file_hash,
        file_size_bytes=file_size,
        mime_type=file.content_type or "application/octet-stream",
        modality=modality,
        is_associated=is_associated,
        association_notes=association_notes
    )
    db.add(db_file)
    db.commit()
    db.refresh(db_file)

    log_audit_event(
        db=db,
        action="FILE_UPLOADED",
        resource_type="FILE",
        resource_id=str(db_file.id),
        user=current_user,
        details={
            "case_id": case_id,
            "filename": orig_name,
            "modality": modality.value,
            "size_bytes": file_size,
            "file_hash": file_hash,
            "deidentified_attested": True,
        }
    )

    return db_file


@router.get("/cases/{case_id}/uploads", response_model=List[FileUploadResponse])
def list_case_files(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    case = verify_case_access(case_id, current_user, db, access="read")
    return case.files


@router.get("/uploads/{file_id}", response_model=FileUploadResponse)
def get_file_metadata(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    file_record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    verify_case_access(file_record.case_id, current_user, db, access="read")
    return file_record


@router.get("/uploads/{file_id}/content")
def download_file(
    file_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Safely serves stored static files (e.g. uploaded images, Grad-CAM overlays).
    Guards strictly against directory traversal attacks.
    """
    file_record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, current_user, db, access="read")
    target_path = Path(file_record.file_path)

    if not target_path.exists() or not target_path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    # Prevent symlink traversal outside UPLOAD_DIR
    try:
        resolved_path = target_path.resolve(strict=True)
        upload_root = UPLOAD_DIR.resolve(strict=True)
    except (OSError, RuntimeError):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid path resolution.")
    if not resolved_path.is_relative_to(upload_root):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Illegal file path access.")

    # Decrypts chunk by chunk when the file is encrypted at rest; plaintext legacy files pass through.
    return StreamingResponse(
        upload_store.stream(target_path),
        media_type=file_record.mime_type,
        headers={"Content-Disposition": f'attachment; filename="{quote(file_record.filename)}"', "Content-Length": str(file_record.file_size_bytes)},
    )


class FileAssociationUpdate(BaseModel):
    is_associated: bool
    association_notes: Optional[str] = None


@router.patch("/uploads/{file_id}/association", response_model=FileUploadResponse)
def update_file_association(
    file_id: int,
    assoc_in: FileAssociationUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Updates the clinical association status of a file.
    Guarantees: Unassociated files are strictly prevented from entering case-level fusion or inference.
    """
    file_record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")

    verify_case_access(file_record.case_id, current_user, db)

    file_record.is_associated = assoc_in.is_associated
    if assoc_in.association_notes is not None:
        file_record.association_notes = assoc_in.association_notes

    db.commit()
    db.refresh(file_record)

    log_audit_event(
        db=db,
        action="FILE_ASSOCIATION_UPDATED",
        resource_type="FILE",
        resource_id=str(file_record.id),
        user=current_user,
        details={
            "case_id": file_record.case_id,
            "filename": file_record.filename,
            "is_associated": file_record.is_associated,
            "association_notes": file_record.association_notes
        }
    )

    return file_record
