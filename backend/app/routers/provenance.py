"""Case-scoped evidence provenance and audit-history endpoints."""

from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import AuditEvent, Examination, Finding, UploadedFile, User
from app.schemas.entities import AuditEventResponse
from app.services.auth import get_current_user, verify_case_access


router = APIRouter(tags=["Evidence Provenance"])


@router.get("/cases/{case_id}/provenance", response_model=List[AuditEventResponse])
def get_case_provenance(
    case_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Return persisted metadata-only audit events authorized for one case."""
    verify_case_access(case_id, current_user, db, access="read")

    resource_ids = {
        "CASE": {str(case_id)},
        "EXAMINATION": {
            str(row.id) for row in db.query(Examination.id).filter(Examination.case_id == case_id).all()
        },
        "FILE": {
            str(row.id) for row in db.query(UploadedFile.id).filter(UploadedFile.case_id == case_id).all()
        },
        "FINDING": {
            str(row.id) for row in db.query(Finding.id).filter(Finding.case_id == case_id).all()
        },
    }

    matching = []
    events = db.query(AuditEvent).order_by(AuditEvent.timestamp.desc()).all()
    for event in events:
        details = event.details or {}
        has_case_detail = str(details.get("case_id", "")) == str(case_id)
        has_case_resource = event.resource_id in resource_ids.get(event.resource_type, set())
        if has_case_detail or has_case_resource:
            matching.append(event)
            if len(matching) >= limit:
                break
    return matching
