"""Evidence-gated longitudinal forecasting eligibility for MedTwin.

The service only uses source-linked numeric laboratory results with an explicit
collection time, matching metric, and matching unit. Examination dates alone are
never converted into invented measurements.

Sufficient observations are necessary but not sufficient: a forecast also needs a
forecasting model evaluated on a chronological held-out split (manuscript
Algorithm 1, step 11). No such model is registered, so eligible data return
NOT_ELIGIBLE with MODEL_NOT_VALIDATED and the observed series only. Persistence
and linear extrapolations are not emitted, because an untested extrapolation is
still a prediction.
"""

from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import L_MIN_OBSERVATIONS
from app.models.entities import EvidenceStatus, ForecastRecord, LabInvestigationReport


def _parse_collection_time(value: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 collection time; ambiguous free-form dates are rejected."""
    if not value:
        return None
    normalized = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _matching_numeric_series(
    case_id: int,
    db: Session,
    target_metric: str,
    unit: str,
) -> List[Dict[str, Any]]:
    target_key = target_metric.strip().casefold()
    unit_key = unit.strip().casefold()
    series: List[Dict[str, Any]] = []

    reports = (
        db.query(LabInvestigationReport)
        .filter(LabInvestigationReport.case_id == case_id)
        .order_by(LabInvestigationReport.id.asc())
        .all()
    )
    for report in reports:
        payload = report.test_results_json or {}
        collected_at = _parse_collection_time(report.collection_time)
        if collected_at is None and isinstance(payload, dict):
            collected_at = _parse_collection_time(payload.get("collection_date"))
        if collected_at is None:
            continue
        results = payload.get("results", []) if isinstance(payload, dict) else payload
        for result in results:
            result_name = str(result.get("test_name", "")).strip().casefold()
            result_code = str(result.get("code", "")).strip().casefold()
            result_unit = str(result.get("unit", "")).strip().casefold()
            if target_key not in {result_name, result_code} or unit_key != result_unit:
                continue
            try:
                value = float(result["result_value"])
            except (KeyError, TypeError, ValueError):
                continue
            if not np.isfinite(value):
                continue
            series.append({
                "report_id": report.id,
                "date": collected_at.isoformat(),
                "timestamp": collected_at.timestamp(),
                "metric": target_metric,
                "value": value,
                "unit": unit,
                "source": "LAB_REPORT",
            })

    series.sort(key=lambda item: item["timestamp"])
    return series


def _store_ineligible(
    case_id: int,
    db: Session,
    target_metric: str,
    unit: str,
    horizon_days: int,
    series: List[Dict[str, Any]],
    reason: str,
) -> Dict[str, Any]:
    record = ForecastRecord(
        case_id=case_id,
        target_metric=target_metric,
        unit=unit,
        horizon_days=horizon_days,
        observations_count=len(series),
        predicted_value=None,
        baseline_persistence=None,
        baseline_linear=None,
        mae_estimate=None,
        rmse_estimate=None,
        eligibility_status=EvidenceStatus.NOT_ELIGIBLE,
        ineligibility_reason=reason,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return {
        "id": record.id,
        "case_id": case_id,
        "target_metric": target_metric,
        "unit": unit,
        "horizon_days": horizon_days,
        "observations_count": len(series),
        "predicted_value": None,
        "baseline_persistence": None,
        "baseline_linear": None,
        "mae_estimate": None,
        "rmse_estimate": None,
        "eligibility_status": EvidenceStatus.NOT_ELIGIBLE.value,
        "ineligibility_reason": reason,
        "chronological_series": series,
        "notice": "FORECAST UNAVAILABLE. No clinical prediction was produced.",
    }


def evaluate_case_forecasting(
    case_id: int,
    db: Session,
    target_metric: str = "Joint Space Width",
    unit: str = "mm",
    horizon_days: int = 180,
) -> Dict[str, Any]:
    """Evaluate data and model eligibility; no forecast is produced without a validated model."""
    series = _matching_numeric_series(case_id, db, target_metric, unit)

    db.query(ForecastRecord).filter(
        ForecastRecord.case_id == case_id,
        ForecastRecord.target_metric == target_metric,
    ).delete()

    if not series:
        return _store_ineligible(
            case_id,
            db,
            target_metric,
            unit,
            horizon_days,
            series,
            "NOT_ELIGIBLE: No source-linked numeric observations match the requested target and unit with valid collection dates.",
        )
    if len(series) == 1:
        return _store_ineligible(
            case_id,
            db,
            target_metric,
            unit,
            horizon_days,
            series,
            "NOT_ELIGIBLE: A single comparable observation cannot establish a longitudinal trend.",
        )
    if len(series) < L_MIN_OBSERVATIONS:
        return _store_ineligible(
            case_id,
            db,
            target_metric,
            unit,
            horizon_days,
            series,
            f"NOT_ELIGIBLE: Insufficient comparable observations ({len(series)} available, minimum {L_MIN_OBSERVATIONS} required).",
        )

    t_vals = np.array([item["timestamp"] for item in series], dtype=float)
    t_rel_days = (t_vals - t_vals[0]) / 86400.0
    if len(np.unique(t_rel_days)) < L_MIN_OBSERVATIONS:
        return _store_ineligible(
            case_id,
            db,
            target_metric,
            unit,
            horizon_days,
            series,
            "NOT_ELIGIBLE: Comparable observations require at least three distinct collection dates.",
        )

    result = _store_ineligible(
        case_id,
        db,
        target_metric,
        unit,
        horizon_days,
        series,
        "MODEL_NOT_VALIDATED: The observations meet the data requirement, but no forecasting model has been "
        "evaluated on a chronological held-out split. Observed values are listed; no forecast was produced.",
    )
    return {**result, "data_eligibility": "SUFFICIENT_OBSERVATIONS"}
