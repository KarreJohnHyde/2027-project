"""Case-authorized, append-only demographic context entered by verified reviewers.

No source text, extracted attribute, measurement, range, risk or eGFR is changed.
The context is explicit rather than a silent fallback for missing OCR headers.
"""

from datetime import date
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import AuditEvent, ReviewedDemographics, UploadedFile, User, UserRole, VerificationStatus
from app.request_context import get_request_id
from app.services.auth import get_current_user, require_role, verify_case_access

router = APIRouter(prefix="/cases", tags=["Reviewed demographic context"])
NOTICE = (
    "Reviewer-entered context is not source-extracted evidence or independent validation. "
    "Original attributes and laboratory intervals remain unchanged. Use only after checking "
    "case identity and the source appropriate to the specimen date."
)


class DemographicsInput(BaseModel):
    expected_revision: int = Field(..., ge=0)
    sex: Literal["M", "F", "UNKNOWN"]
    date_of_birth: Optional[date]
    source_file_id: Optional[int] = Field(..., gt=0)
    reason: str = Field(..., min_length=5, max_length=500)
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    @field_validator("date_of_birth")
    @classmethod
    def not_future(cls, value):
        if value is not None and value > date.today():
            raise ValueError("Date of birth cannot be in the future.")
        return value


def serialize(row: ReviewedDemographics, db: Session) -> dict:
    source = db.get(UploadedFile, row.source_file_id) if row.source_file_id else None
    source_state = "PROVENANCE_UNAVAILABLE"
    if row.source_kind == "REVIEWER_ATTESTATION":
        source_state = "REVIEWER_ATTESTATION"
    elif row.source_kind == "FILE" or row.source_reference_id or row.source_file_id:
        source_state = "ACTIVE" if (
            source and source.case_id == row.case_id and source.is_associated
            and not source.withdrawn_at and not source.superseded_by_file_id
        ) else "WITHDRAWN_OR_UNASSOCIATED"
        if not source:
            source_state = "SOURCE_DELETED"
    return {
        "id": row.id, "case_id": row.case_id, "revision": row.revision,
        "sex": row.sex, "date_of_birth": row.date_of_birth.isoformat() if row.date_of_birth else None,
        "source_file_id": row.source_file_id, "source_reference_id": row.source_reference_id,
        "reason": row.reason,
        "reviewed_by_id": row.reviewed_by_id, "created_at": row.created_at.isoformat(),
        "source_state": source_state, "provenance": "REVIEWER_ENTERED_NOT_SOURCE_EXTRACTED",
    }


@router.get("/{case_id}/demographics")
def get_demographics(case_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    verify_case_access(case_id, user, db, access="read")
    can_record = user.role in (UserRole.CLINICIAN, UserRole.RESEARCHER, UserRole.ADMIN) and user.verification_status == VerificationStatus.VERIFIED
    if can_record:
        try:
            verify_case_access(case_id, user, db, access="write")
        except HTTPException as exc:
            if exc.status_code != 403:
                raise
            can_record = False
    rows = db.query(ReviewedDemographics).filter_by(case_id=case_id).order_by(ReviewedDemographics.revision.desc()).all()
    history = [serialize(row, db) for row in rows]
    return {"case_id": case_id, "current": history[0] if history else None, "history": history, "notice": NOTICE, "can_record": can_record}


@router.post("/{case_id}/demographics", status_code=201)
def record_demographics(
    case_id: int, payload: DemographicsInput, db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.CLINICIAN, UserRole.RESEARCHER)),
):
    verify_case_access(case_id, user, db)
    latest = db.query(ReviewedDemographics).filter_by(case_id=case_id).order_by(ReviewedDemographics.revision.desc()).first()
    revision = latest.revision if latest else 0
    if payload.expected_revision != revision:
        raise HTTPException(409, "Demographic context changed. Reload and review the latest revision before saving.")
    if payload.source_file_id:
        source = db.get(UploadedFile, payload.source_file_id)
        if not source or source.case_id != case_id:
            raise HTTPException(404, "Source file not found in this case.")
        if not source.is_associated or source.withdrawn_at or source.superseded_by_file_id:
            raise HTTPException(409, "Use an active, associated source file; this source is withdrawn, superseded or unassociated.")
    row = ReviewedDemographics(
        case_id=case_id, revision=revision + 1, sex=payload.sex,
        date_of_birth=payload.date_of_birth, source_file_id=payload.source_file_id,
        source_reference_id=payload.source_file_id,
        source_kind="FILE" if payload.source_file_id else "REVIEWER_ATTESTATION",
        reason=payload.reason, reviewed_by_id=user.id,
    )
    try:
        db.add(row)
        db.flush()
        # Commit the context and its privacy-safe audit metadata atomically.
        details = {"case_id": case_id, "revision": row.revision, "source_file_id": row.source_file_id}
        request_id = get_request_id()
        if request_id:
            details["request_id"] = request_id
        db.add(AuditEvent(user_id=user.id, action="DEMOGRAPHIC_CONTEXT_RECORDED", resource_type="REVIEWED_DEMOGRAPHICS", resource_id=str(row.id), details=details))
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(409, "Demographic context changed concurrently. Reload before saving.") from exc
    db.refresh(row)
    return serialize(row, db)
