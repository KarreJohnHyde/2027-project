"""
Multimodal Gated Fusion Router for MedTwin.
Implements Equations 8-10 and Section VI-C of the IEEE manuscript.
"""

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import MultimodalFusionRecord, User
from app.schemas.entities import FusionRequest, FusionResponse
from app.services.auth import get_current_user, verify_case_access
from app.services.fusion_service import evaluate_multimodal_fusion
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["Multimodal Fusion"])


@router.post("/cases/{case_id}/fusion", response_model=FusionResponse)
@router.post("/fusion/{case_id}/evaluate", response_model=FusionResponse)
@router.post("/fusion/{case_id}", response_model=FusionResponse)
def trigger_multimodal_fusion(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Executes Masked Gated Multimodal Fusion on all valid, associated modalities for the case.
    Strictly follows Alg 1:
    - sum(m_k) == 0 -> ABSTAIN (missing input; Eq. 9 is NOT evaluated).
    - sum(m_k) == 1 -> NOT RUN (single modality; fusion adds nothing).
    - sum(m_k) >= 2 -> remains NOT RUN until paired-data and model validation exist.
    """
    verify_case_access(case_id, current_user, db)

    fusion_result = evaluate_multimodal_fusion(case_id, db)

    log_audit_event(
        db=db,
        action="MULTIMODAL_FUSION_EVALUATED",
        resource_type="FUSION",
        resource_id=str(fusion_result.get("id")),
        user=current_user,
        details={
            "case_id": case_id,
            "mask": fusion_result["modality_mask"],
            "status": fusion_result["fused_status"],
            "active_count": fusion_result["active_modalities_count"]
        }
    )

    return fusion_result


@router.get("/cases/{case_id}/fusion", response_model=Optional[FusionResponse])
@router.get("/fusion/{case_id}", response_model=Optional[FusionResponse])
def get_latest_fusion(
    case_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_case_access(case_id, current_user, db, access="read")

    latest_record = db.query(MultimodalFusionRecord).filter(
        MultimodalFusionRecord.case_id == case_id
    ).order_by(MultimodalFusionRecord.created_at.desc()).first()

    if not latest_record:
        # Evaluate now if not yet run
        return evaluate_multimodal_fusion(case_id, db)

    return {
        "id": latest_record.id,
        "case_id": latest_record.case_id,
        "modality_mask": latest_record.modality_mask,
        "active_modalities_count": latest_record.active_modalities_count,
        "gated_weights": latest_record.gated_weights,
        "fused_status": latest_record.fused_status.value,
        "fused_prediction": latest_record.fused_prediction,
        "paired_data_validated": latest_record.paired_data_validated,
        "abstention_reason": latest_record.abstention_reason
    }
