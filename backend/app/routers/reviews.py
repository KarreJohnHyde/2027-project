"""
Human Review and Clinical Feedback Router for MedTwin.
Allows authorized clinicians to record assessments while preserving original model outputs.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import CorrectionDecision, Finding, HumanReview, User, UserRole, EvidenceStatus
from app.schemas.entities import CorrectionDecisionCreate, CorrectionDecisionResponse, HumanReviewCreate, HumanReviewResponse
from app.services.auth import get_current_user, verify_case_access, require_role
from app.services.audit_service import log_audit_event

router = APIRouter(prefix="/reviews", tags=["Human Review"])


@router.post("/{finding_id}", response_model=HumanReviewResponse, status_code=status.HTTP_201_CREATED)
def submit_human_review(
    finding_id: int,
    review_in: HumanReviewCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN))
):
    """
    Submits a clinician review for a finding.
    Guarantees: Original AI output remains completely unchanged and traceable.
    """
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    verify_case_access(finding.case_id, current_user, db)

    correction_payload = None
    if review_in.correction_payload is not None:
        valid_statement_ids = {statement.id for statement in finding.report_statements}
        valid_measurement_ids = {measurement.id for measurement in finding.measurements}
        requested_statement_ids = {
            item.target_statement_id for item in review_in.correction_payload.entity_corrections
        }
        requested_measurement_ids = {
            item.target_measurement_id for item in review_in.correction_payload.measurement_corrections
        }
        unknown_statement_ids = requested_statement_ids - valid_statement_ids
        unknown_measurement_ids = requested_measurement_ids - valid_measurement_ids
        if unknown_statement_ids or unknown_measurement_ids:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail={
                    "code": "CORRECTION_TARGET_NOT_IN_FINDING",
                    "unknown_statement_ids": sorted(unknown_statement_ids),
                    "unknown_measurement_ids": sorted(unknown_measurement_ids),
                },
            )
        correction_payload = review_in.correction_payload.model_dump(mode="json", exclude_none=True)

    review = HumanReview(
        finding_id=finding.id,
        reviewer_id=current_user.id,
        review_status=review_in.review_status,
        reviewer_comments=review_in.reviewer_comments,
        correction_payload=correction_payload,
        original_output_preserved=True
    )
    db.add(review)

    # Update finding review status tag without modifying original predictions
    finding.review_status = EvidenceStatus.COMPLETED
    db.commit()
    db.refresh(review)

    log_audit_event(
        db=db,
        action="HUMAN_REVIEW_SUBMITTED",
        resource_type="FINDING",
        resource_id=str(finding.id),
        user=current_user,
        details={
            "finding_id": finding.id,
            "decision": review_in.review_status,
            "original_output_preserved": True,
            "correction_schema_version": correction_payload.get("schema_version") if correction_payload else None,
            "entity_correction_count": len(correction_payload["entity_corrections"]) if correction_payload else 0,
            "measurement_correction_count": len(correction_payload["measurement_corrections"]) if correction_payload else 0,
        }
    )

    return review


@router.post("/corrections/{review_id}/decision", response_model=CorrectionDecisionResponse, status_code=status.HTTP_201_CREATED)
def decide_correction(
    review_id: int,
    decision_in: CorrectionDecisionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN)),
):
    """
    Approves or rejects a proposed correction. The decision must come from a verified
    reviewer other than the proposer. Approval changes only the effective (reviewed) view;
    the extracted statement or measurement and the original review stay unchanged.
    """
    review = db.query(HumanReview).filter(HumanReview.id == review_id).first()
    if not review:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Review not found.")
    verify_case_access(review.finding.case_id, current_user, db)
    if review.review_status != "MODIFIED" or not review.correction_payload:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail={"code": "NO_CORRECTION_TO_DECIDE"})
    if review.reviewer_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail={"code": "FOUR_EYES_REQUIRED", "message": "A correction must be decided by a reviewer other than its proposer."})
    if review.decision is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "CORRECTION_ALREADY_DECIDED", "decision": review.decision.decision})

    decision = CorrectionDecision(
        review_id=review.id,
        decided_by_id=current_user.id,
        decision=decision_in.decision,
        rationale=decision_in.rationale,
    )
    db.add(decision)
    db.commit()
    db.refresh(decision)
    log_audit_event(
        db=db,
        action=f"CORRECTION_{decision_in.decision}",
        resource_type="HUMAN_REVIEW",
        resource_id=str(review.id),
        user=current_user,
        details={
            "finding_id": review.finding_id,
            "proposed_by_id": review.reviewer_id,
            "original_output_preserved": True,
            "applies_to": "EFFECTIVE_VIEW_ONLY" if decision_in.decision == "APPROVED" else "NONE",
        },
    )
    return decision


@router.get("/{finding_id}", response_model=List[HumanReviewResponse])
def get_finding_reviews(
    finding_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    verify_case_access(finding.case_id, current_user, db, access="read")
    return finding.reviews
