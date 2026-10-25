"""
Human Review and Clinical Feedback Router for MedTwin.
Allows authorized clinicians to record assessments while preserving original model outputs.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Finding, HumanReview, User, UserRole, EvidenceStatus
from app.schemas.entities import HumanReviewCreate, HumanReviewResponse
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
