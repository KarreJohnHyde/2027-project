"""
Clinical Report Concordance Router for MedTwin.
Flags discordance between model findings and narrative clinical text without modifying either source.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User
from app.schemas.entities import ConcordanceResponse
from app.services.auth import get_current_user, verify_case_access
from app.services.concordance_service import evaluate_report_concordance
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["Report Concordance"])


@router.post("/cases/{case_id}/concordance", response_model=ConcordanceResponse)
@router.post("/concordance/{case_id}/evaluate", response_model=ConcordanceResponse)
@router.post("/concordance/{case_id}", response_model=ConcordanceResponse)
def run_concordance_check(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Evaluates concordance between clinical report assertions and image/ECG findings.
    Preserves both original sources; flags discordances for human clinician review.
    """
    verify_case_access(case_id, current_user, db)

    result = evaluate_report_concordance(case_id, db)

    log_audit_event(
        db=db,
        action="REPORT_CONCORDANCE_CHECKED",
        resource_type="CONCORDANCE",
        user=current_user,
        details={
            "case_id": case_id,
            "total": result["total_comparisons"],
            "discordant": result["discordant_count"]
        }
    )

    return result


@router.get("/cases/{case_id}/concordance", response_model=ConcordanceResponse)
@router.get("/concordance/{case_id}", response_model=ConcordanceResponse)
def get_concordance_status(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_case_access(case_id, current_user, db, access="read")
    return evaluate_report_concordance(case_id, db)
