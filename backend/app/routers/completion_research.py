"""Authorized, read-only completion research endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.entities import User
from app.services.auth import get_current_user, verify_case_access
from app.services import completion_research
from app.schemas.completion_research import PairedEvidenceResponse, BacktestResponse

router = APIRouter(tags=["Completion research"])


@router.get("/cases/{case_id}/research/paired-evidence", response_model=PairedEvidenceResponse)
def paired(case_id: int, exam_id: int | None = Query(None, gt=0), confirmed_same_patient: bool = False,
           db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read")
    return completion_research.paired_evidence(case, db, exam_id, confirmed_same_patient)


@router.get("/cases/{case_id}/research/backtest", response_model=BacktestResponse)
def baseline_backtest(case_id: int, metric: str = Query(..., min_length=1, max_length=128),
                     unit: str = Query(..., min_length=1, max_length=32), horizon_days: int = Query(30, ge=1, le=3650),
                     db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read")
    return completion_research.backtest(case, db, metric, unit, horizon_days)


@router.get("/universal/research/audit")
def public_research_audit(current_user: User = Depends(get_current_user)):
    return completion_research.audit_summary()
