"""Patient and caregiver portal: account-scoped documents and reviewed results.

A clinician who manages a case links a person's account to it with a PATIENT or CAREGIVER
membership (/cases/{id}/members); a patient can also add or remove their own caregivers here.
These memberships never open the clinical endpoints (verify_case_access admits only VIEWER and
EDITOR members). Public users can create a private portal case and upload de-identified files.
The portal shows only:
  * the documents uploaded to the case, as uploaded;
  * numeric results from report findings a clinician has confirmed, with the values of approved
    corrections, and the reference interval and flag printed on the source report.
Research-model output and anything not yet reviewed are never shown.
"""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.config import RATE_LIMIT_UPLOAD_PER_MINUTE, UPLOAD_DIR
from app.database import get_db
from app.models.entities import Case, CaseMembership, Finding, HumanReview, MedicalMeasurement, UploadedFile, User, UserRole
from app.schemas.entities import FileUploadResponse
from app.security import rate_limit
from app.services import upload_store
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user
from app.services.effective_evidence import approved_measurement_overrides
from app.services.file_storage import save_uploaded_file
from app.services.measurement_identity import duplicate_map

router = APIRouter(prefix="/portal", tags=["Patient and caregiver portal"])

PORTAL_ROLES = ("PATIENT", "CAREGIVER")
REVIEWED = {"CONFIRMED", "MODIFIED"}
NOT_SHOWN = ("Results appear here after your clinician has reviewed the report they come from. Research-model output and "
             "results awaiting review are not shown. This page is not a diagnosis; ask your care team about any result.")
PRIVATE_RECORD_NOTICE = (
    "Documents in this private record are stored for you to view and download. No clinical interpretation or "
    "diagnosis is generated here. Ask your care team to review any document."
)


def _membership(case_id: int, user: User, db: Session) -> CaseMembership:
    membership = db.query(CaseMembership).filter(
        CaseMembership.case_id == case_id, CaseMembership.user_id == user.id, CaseMembership.role.in_(PORTAL_ROLES),
    ).first()
    if membership is None:  # the same answer whether or not the case exists
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No record is shared with you under this id.")
    return membership


def _reviewed_findings(db: Session, case_id: int) -> set[int]:
    """Findings whose latest clinician review confirmed them, excluding research-model output."""
    latest: dict[int, HumanReview] = {}
    rows = (db.query(HumanReview).join(Finding, Finding.id == HumanReview.finding_id)
            .filter(Finding.case_id == case_id).order_by(HumanReview.reviewed_at.asc(), HumanReview.id.asc()).all())
    for review in rows:
        latest[review.finding_id] = review
    reviewed = set()
    for finding_id, review in latest.items():
        finding = db.get(Finding, finding_id)
        research = (finding.evidence_provenance or {}).get("source") == "MODEL_INFERENCE"
        if review.review_status in REVIEWED and not research:
            reviewed.add(finding_id)
    return reviewed


def _results(db: Session, case_id: int) -> list[dict]:
    measurements = (db.query(MedicalMeasurement).filter(MedicalMeasurement.case_id == case_id)
                    .order_by(MedicalMeasurement.created_at.asc(), MedicalMeasurement.id.asc()).all())
    reviewed = _reviewed_findings(db, case_id)
    duplicates = duplicate_map(measurements)
    overrides = approved_measurement_overrides(db, case_id)
    results = []
    for item in measurements:
        if item.finding_id not in reviewed or item.id in duplicates:
            continue
        override = overrides.get(item.id, {})
        if override.get("removed"):
            continue
        fields = override.get("fields", {})
        results.append({
            "name": fields.get("display_name", item.display_name),
            "value": fields.get("value", item.value),
            "comparator": fields.get("result_operator", item.result_operator or "="),
            "unit": fields.get("unit", item.unit),
            "reference_low": fields.get("reference_low", item.reference_low),
            "reference_high": fields.get("reference_high", item.reference_high),
            "reference_source": "PRINTED_ON_REPORT" if item.reference_source == "DOCUMENTED_IN_SOURCE" else "NOT_PRINTED",
            "documented_flag": item.documented_flag,
            "documented_date": item.documented_date,
            "source_document_id": item.source_file_id,
            "corrected_by_review": bool(fields),
        })
    return results


def _documents(db: Session, case_id: int) -> list[dict]:
    uploads = (db.query(UploadedFile).filter(UploadedFile.case_id == case_id, UploadedFile.is_associated.is_(True),
                                             UploadedFile.withdrawn_at.is_(None)).order_by(UploadedFile.id.asc()).all())
    return [{"id": upload.id, "filename": upload.filename, "kind": upload.modality.value, "size_bytes": upload.file_size_bytes,
             "uploaded_at": upload.uploaded_at.isoformat() if getattr(upload, "uploaded_at", None) else None} for upload in uploads]


@router.get("/cases")
def list_portal_cases(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    rows = (db.query(CaseMembership, Case).join(Case, Case.id == CaseMembership.case_id)
            .filter(CaseMembership.user_id == current_user.id, CaseMembership.role.in_(PORTAL_ROLES)).all())
    return [{"case_id": case.id, "record": case.pseudonymous_id, "relationship": membership.role} for membership, case in rows]


@router.post("/cases", status_code=status.HTTP_201_CREATED)
def create_personal_record(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    if current_user.role != UserRole.PUBLIC:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Personal records are available to public accounts.")

    existing = (db.query(CaseMembership, Case).join(Case, Case.id == CaseMembership.case_id)
                .filter(CaseMembership.user_id == current_user.id, CaseMembership.role == "PATIENT").first())
    if existing is not None:
        membership, case = existing
        return {"case_id": case.id, "record": case.pseudonymous_id, "relationship": membership.role}

    case = Case(
        pseudonymous_id=f"PERSONAL-{uuid4().hex.upper()}",
        description="Private personal record. Uploaded documents require a de-identification attestation.",
        created_by_id=None,
    )
    db.add(case)
    db.flush()
    db.add(CaseMembership(case_id=case.id, user_id=current_user.id, role="PATIENT", granted_by_id=current_user.id))
    db.commit()
    db.refresh(case)
    log_audit_event(db=db, action="PERSONAL_RECORD_CREATED", resource_type="CASE", resource_id=str(case.id), user=current_user)
    return {"case_id": case.id, "record": case.pseudonymous_id, "relationship": "PATIENT"}


@router.get("/cases/{case_id}")
def get_portal_record(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    membership = _membership(case_id, current_user, db)
    case = db.get(Case, case_id)
    notice = NOT_SHOWN if case is not None and case.created_by_id is not None else PRIVATE_RECORD_NOTICE
    record = {"case_id": case_id, "relationship": membership.role, "documents": _documents(db, case_id), "results": _results(db, case_id),
              "notice": notice}
    log_audit_event(db=db, action="PORTAL_RECORD_VIEWED", resource_type="CASE", resource_id=str(case_id), user=current_user,
                    details={"relationship": membership.role, "results": len(record["results"])})
    return record


@router.get("/cases/{case_id}/documents/{upload_id}")
def download_portal_document(case_id: int, upload_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _membership(case_id, current_user, db)
    upload = db.get(UploadedFile, upload_id)
    if upload is None or upload.case_id != case_id or not upload.is_associated or upload.withdrawn_at is not None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Document not found.")
    log_audit_event(db=db, action="PORTAL_DOCUMENT_DOWNLOADED", resource_type="UPLOAD", resource_id=str(upload_id), user=current_user,
                    details={"case_id": case_id})
    return StreamingResponse(upload_store.stream(Path(upload.file_path)), media_type=upload.mime_type or "application/octet-stream",
                             headers={"Content-Disposition": f'attachment; filename="{upload.filename}"', "Cache-Control": "no-store"})


@router.post(
    "/cases/{case_id}/documents",
    response_model=FileUploadResponse,
    status_code=status.HTTP_201_CREATED,
    dependencies=[Depends(rate_limit("upload", RATE_LIMIT_UPLOAD_PER_MINUTE))],
)
async def upload_personal_document(
    case_id: int,
    file: UploadFile = File(...),
    deidentified: bool = Form(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _patient(case_id, current_user, db)
    if not deidentified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Upload rejected: de-identified research-data attestation is required.",
        )

    original_name, stored_name, file_hash, file_size, modality = await save_uploaded_file(file)
    existing = db.query(UploadedFile).filter(
        UploadedFile.case_id == case_id,
        UploadedFile.file_hash == file_hash,
    ).first()
    if existing is not None:
        log_audit_event(
            db=db,
            action="FILE_UPLOAD_IDEMPOTENT_HIT",
            resource_type="FILE",
            resource_id=str(existing.id),
            user=current_user,
            details={"case_id": case_id, "file_hash": file_hash, "deidentified_attested": True},
        )
        return existing

    upload = UploadedFile(
        case_id=case_id,
        examination_id=None,
        filename=original_name,
        stored_filename=stored_name,
        file_path=str(UPLOAD_DIR / stored_name),
        file_hash=file_hash,
        file_size_bytes=file_size,
        mime_type=file.content_type or "application/octet-stream",
        modality=modality,
        is_associated=True,
        association_notes="Patient-uploaded de-identified document",
    )
    db.add(upload)
    db.commit()
    db.refresh(upload)
    log_audit_event(
        db=db,
        action="FILE_UPLOADED",
        resource_type="FILE",
        resource_id=str(upload.id),
        user=current_user,
        details={
            "case_id": case_id,
            "filename": original_name,
            "modality": modality.value,
            "size_bytes": file_size,
            "file_hash": file_hash,
            "deidentified_attested": True,
            "upload_context": "PERSONAL_PORTAL",
        },
    )
    return upload


class CaregiverRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=64)

    model_config = ConfigDict(extra="forbid")


def _patient(case_id: int, user: User, db: Session) -> CaseMembership:
    membership = _membership(case_id, user, db)
    if membership.role != "PATIENT":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the patient can manage caregivers.")
    return membership


@router.get("/cases/{case_id}/caregivers")
def list_caregivers(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _patient(case_id, current_user, db)
    rows = (db.query(CaseMembership, User).join(User, User.id == CaseMembership.user_id)
            .filter(CaseMembership.case_id == case_id, CaseMembership.role == "CAREGIVER").all())
    return [{"user_id": member.id, "username": member.username, "since": membership.created_at.isoformat()} for membership, member in rows]


@router.post("/cases/{case_id}/caregivers", status_code=status.HTTP_201_CREATED)
def add_caregiver(case_id: int, payload: CaregiverRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _patient(case_id, current_user, db)
    caregiver = db.query(User).filter(User.username == payload.username, User.is_active.is_(True)).first()
    if caregiver is None or caregiver.id == current_user.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No other active account with that username.")
    case = db.get(Case, case_id)
    existing = db.query(CaseMembership).filter(CaseMembership.case_id == case_id, CaseMembership.user_id == caregiver.id).first()
    if case.created_by_id == caregiver.id or (existing is not None and existing.role not in PORTAL_ROLES):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That account already has clinical access to this record.")
    if existing is None:
        db.add(CaseMembership(case_id=case_id, user_id=caregiver.id, role="CAREGIVER", granted_by_id=current_user.id))
    elif existing.role == "PATIENT":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="That account is linked as the patient.")
    db.commit()
    log_audit_event(db=db, action="PORTAL_CAREGIVER_GRANTED", resource_type="CASE", resource_id=str(case_id), user=current_user,
                    details={"caregiver_user_id": caregiver.id})
    return {"user_id": caregiver.id, "username": caregiver.username}


@router.delete("/cases/{case_id}/caregivers/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_caregiver(case_id: int, user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    _patient(case_id, current_user, db)
    membership = db.query(CaseMembership).filter(CaseMembership.case_id == case_id, CaseMembership.user_id == user_id,
                                                 CaseMembership.role == "CAREGIVER").first()
    if membership is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caregiver not found.")
    db.delete(membership)
    db.commit()
    log_audit_event(db=db, action="PORTAL_CAREGIVER_REVOKED", resource_type="CASE", resource_id=str(case_id), user=current_user,
                    details={"caregiver_user_id": user_id})
