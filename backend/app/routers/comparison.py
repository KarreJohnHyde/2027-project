"""
Longitudinal Comparison Router (Old Self vs. New Self).
Implements Section IX endpoints for semantic report diffing and numeric delta analytics.
"""

from typing import Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User
from app.services.auth import get_current_user, verify_case_access
from app.services.comparison_service import ComparisonService
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/cases", tags=["Longitudinal Comparison"])


class CompareRequest(BaseModel):
    prior_exam_id: Optional[int] = None
    current_exam_id: Optional[int] = None


@router.post("/{case_id}/compare")
def compare_case_examinations(
    case_id: int,
    payload: Optional[CompareRequest] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Executes longitudinal Old-Self vs. New-Self comparison across report versions,
    numeric measurement deltas, medical radiographs, and 3D digital twin states.
    Strictly prevents cross-case comparison.
    """
    case = verify_case_access(case_id, current_user, db)

    prior_id = payload.prior_exam_id if payload else None
    current_id = payload.current_exam_id if payload else None

    result = ComparisonService.compare_examinations(
        db=db,
        case=case,
        prior_exam_id=prior_id,
        current_exam_id=current_id
    )

    log_audit_event(
        db=db,
        action="LONGITUDINAL_COMPARISON_RUN",
        resource_type="CASE",
        resource_id=str(case.id),
        user=current_user,
        details={
            "case_id": case.id,
            "prior_exam_id": prior_id,
            "current_exam_id": current_id,
            "status": result.get("status"),
            "semantic_diff_count": len(result.get("semantic_report_diff", [])),
            "numeric_delta_count": len(result.get("numeric_deltas", [])),
        },
    )

    return result
