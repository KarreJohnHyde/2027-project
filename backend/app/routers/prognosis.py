"""Prognosis Studio, risk registry, and clinical calculator endpoints."""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import PrognosisEvaluation, User
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user, verify_case_access
from app.services.biomarker_trends import build_series
from app.services.clinical_calculators import egfr_for_case
from app.services.prognosis_registry import CAPABILITIES_BY_ID, capability_registry, evaluate_scenarios
from app.services.risk_registry import risk_registry

router = APIRouter(tags=["Prognosis, Risk & Trends"])


@router.get("/prognosis/capabilities")
def get_prognosis_capabilities(current_user: User = Depends(get_current_user)):
    return capability_registry()


class ScenarioRequest(BaseModel):
    case_id: int
    organ_system: str = Field(..., max_length=32)
    intervention_id: Optional[str] = Field(None, max_length=64)
    horizon_days: int = Field(365, ge=1, le=3650)


@router.post("/prognosis/evaluate")
def evaluate_prognosis(payload: ScenarioRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Evaluate Scenario A/B availability for a case. Persisted and audited."""
    verify_case_access(payload.case_id, current_user, db, access="read")
    if payload.organ_system not in CAPABILITIES_BY_ID:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Unknown organ system '{payload.organ_system}'.")
    result = evaluate_scenarios(db, payload.case_id, payload.organ_system, payload.intervention_id, payload.horizon_days)
    record = PrognosisEvaluation(
        case_id=payload.case_id,
        organ_system=payload.organ_system,
        intervention_id=payload.intervention_id,
        horizon_days=payload.horizon_days,
        status=result["status"],
        result={key: result[key] for key in ("status", "scenarios", "treatment_effect", "notice")},
        requested_by_id=current_user.id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    log_audit_event(
        db=db, action="PROGNOSIS_EVALUATION_REQUESTED", resource_type="CASE", resource_id=str(payload.case_id), user=current_user,
        details={"organ_system": payload.organ_system, "horizon_days": payload.horizon_days, "status": result["status"], "evaluation_id": record.id},
    )
    return {**result, "evaluation_id": record.id, "evaluated_at": record.created_at.isoformat()}


@router.get("/cases/{case_id}/prognosis-evaluations")
def list_prognosis_evaluations(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    rows = db.query(PrognosisEvaluation).filter(PrognosisEvaluation.case_id == case_id).order_by(PrognosisEvaluation.created_at.desc()).limit(100).all()
    return [
        {"id": row.id, "organ_system": row.organ_system, "intervention_id": row.intervention_id, "horizon_days": row.horizon_days, "status": row.status, "created_at": row.created_at.isoformat()}
        for row in rows
    ]


@router.get("/risk/registry")
def get_risk_registry(current_user: User = Depends(get_current_user)):
    return risk_registry()


@router.get("/cases/{case_id}/biomarker-trends")
def get_biomarker_trends(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Dated, unit-compatible series with tiered descriptive statistics (never forecasts)."""
    verify_case_access(case_id, current_user, db, access="read")
    return {"case_id": case_id, "series": build_series(db, case_id)}


@router.get("/cases/{case_id}/calculations/egfr")
def get_case_egfr(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    return egfr_for_case(db, case_id)
