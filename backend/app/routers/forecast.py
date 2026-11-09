"""
Longitudinal Forecasting and Timeline Router for MedTwin.
Implements Equations 13-14, Section VI-E, and Line 18 of Algorithm 1.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User, ForecastRecord
from app.schemas.entities import ForecastRequest, ForecastResponse
from app.services.auth import get_current_user, verify_case_access
from app.services.forecasting_service import evaluate_case_forecasting
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["Longitudinal Forecasting"])


@router.get("/cases/{case_id}/forecast-history")
def get_forecast_history(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    rows = db.query(ForecastRecord).filter(ForecastRecord.case_id == case_id).order_by(ForecastRecord.id.desc()).limit(100).all()
    fields = ("id", "case_id", "target_metric", "unit", "horizon_days", "observations_count", "predicted_value",
              "baseline_analysis", "eligibility_status", "ineligibility_reason", "notice", "created_at")
    return [{field: getattr(row, field) for field in fields} for row in rows]


@router.post("/cases/{case_id}/forecast", response_model=ForecastResponse)
@router.post("/forecast/{case_id}/evaluate", response_model=ForecastResponse)
@router.post("/forecast/{case_id}", response_model=ForecastResponse)
def compute_case_forecast(
    case_id: int,
    forecast_req: ForecastRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Computes eligible longitudinal forecasts against persistence and linear baselines.
    Enforces minimum history requirement (L >= L_min = 3).
    Returns explicit NOT_ELIGIBLE status if observations are insufficient.
    """
    verify_case_access(case_id, current_user, db)
    if forecast_req.case_id != case_id:
        raise HTTPException(status_code=400, detail="CASE_ID_MISMATCH")
    if forecast_req.method != "eligibility_only":
        if not forecast_req.same_patient_confirmed:
            raise HTTPException(status_code=400, detail="Confirm that the historical observations belong to the same patient.")
        from app.services.research_baselines import evaluate
        result = evaluate(case_id, db, forecast_req.target_metric, forecast_req.unit, forecast_req.horizon_days, forecast_req.method)
    else:
        result = evaluate_case_forecasting(
            case_id=case_id,
            db=db,
            target_metric=forecast_req.target_metric,
            unit=forecast_req.unit,
            horizon_days=forecast_req.horizon_days
        )

    log_audit_event(
        db=db,
        action="FORECAST_EVALUATED",
        resource_type="FORECAST",
        user=current_user,
        details={
            "case_id": case_id,
            "metric": forecast_req.target_metric,
            "status": result["eligibility_status"],
            "obs_count": result["observations_count"]
        }
    )

    return result


@router.get("/cases/{case_id}/forecast", response_model=ForecastResponse)
@router.get("/cases/{case_id}/forecasts")
@router.get("/forecast/{case_id}", response_model=ForecastResponse)
def get_case_forecast(
    case_id: int,
    target_metric: str = Query("Joint Space Width", min_length=1, max_length=128),
    unit: str = Query("mm", min_length=1, max_length=32),
    horizon_days: int = Query(180, ge=1, le=3650),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    verify_case_access(case_id, current_user, db, access="read")
    res = evaluate_case_forecasting(
        case_id=case_id,
        db=db,
        target_metric=target_metric,
        unit=unit,
        horizon_days=horizon_days,
        persist=False,
    )
    # If route called was /forecasts list, wrap in list if needed or return single
    return res
