"""Chronological research baselines on reviewed, source-linked measurements.

Local rolling-origin backtesting is descriptive software evaluation, not external
validation of a disease prognosis. Sparse or ambiguous series return no forecast.
"""
from __future__ import annotations

from datetime import timedelta
import math

import numpy as np
from sqlalchemy.orm import Session

from app.models.entities import EvidenceStatus, ForecastRecord, MedicalMeasurement
from app.services.anatomy_evidence import _latest_reviews
from app.services.effective_evidence import approved_measurement_overrides
from app.services.evidence_synthesis import eligible_upload
from app.services.forecasting_service import _parse_collection_time
from app.services.biomarker_trends import IDENTITY_REVIEW_SERIES
from app.services.terminology import ANALYTES_BY_NAME

VERSION = "chronological-baselines-v1"


def evaluate(case_id: int, db: Session, metric: str, unit: str, horizon_days: int, method: str) -> dict:
    if method not in {"persistence", "linear"} or not 1 <= horizon_days <= 3650:
        raise ValueError("Unsupported baseline or horizon.")
    measurements = db.query(MedicalMeasurement).filter(MedicalMeasurement.case_id == case_id).all()
    reviews = _latest_reviews(db, {m.finding_id for m in measurements})
    overrides = approved_measurement_overrides(db, case_id)
    points = {}
    contexts = set()
    ambiguity = False
    context_missing = False
    lesion_identity_required = False
    for measurement in measurements:
        upload = measurement.source_file
        review = reviews.get(measurement.finding_id)
        if not eligible_upload(upload, case_id) or not review or review.review_status != "CONFIRMED" or not review.original_output_preserved:
            continue
        if measurement.finding.case_id != case_id or measurement.finding.failure_reason or (measurement.finding.inference_run and measurement.finding.inference_run.file_id != upload.id):
            continue
        override = overrides.get(measurement.id, {})
        if override.get("removed"):
            continue
        fields = override.get("fields", {})
        name = fields.get("display_name", measurement.display_name)
        if metric.strip().casefold() not in {name.casefold(), measurement.name.casefold(), (measurement.canonical_code or "").casefold()}:
            continue
        if fields.get("unit", measurement.unit).casefold() != unit.strip().casefold():
            continue
        if fields.get("result_operator", measurement.result_operator or "=") != "=":
            continue
        date = _parse_collection_time(measurement.documented_date)
        value = fields.get("value", measurement.value)
        if date is None or not math.isfinite(value):
            continue
        spatial_metric = measurement.name.casefold().replace(" ", "_") in IDENTITY_REVIEW_SERIES | {"lesion_volume", "edema_volume", "tumor_volume", "tumour_volume"}
        lesion_identity_required |= spatial_metric
        context = tuple(str(fields.get(field, getattr(measurement, field)) or "").strip().casefold() for field in ("specimen", "laboratory_method"))
        contexts.add(context)  # Include duplicate-date sources before deduplication.
        analyte = ANALYTES_BY_NAME.get(measurement.name)
        if analyte and analyte.association != "PHYSIOLOGICAL_SIGNAL" and not spatial_metric:
            context_missing |= any(part in {"", "not_documented", "not documented", "unknown", "not available"} for part in context)
        # Multiple values at one date cannot be arbitrarily chosen or averaged.
        key = date.isoformat()
        if key in points and points[key]["value"] != value:
            ambiguity = True
        if key in points:
            points[key]["measurement_ids"].append(measurement.id)
            continue
        points[key] = {"date": key, "value": float(value), "unit": unit,
                       "measurement_ids": [measurement.id], "upload_id": upload.id, "sha256": upload.file_hash,
                       "page": measurement.source_page, "source_span": measurement.source_span,
                       "review_id": review.id}
    series = sorted(points.values(), key=lambda p: p["date"])
    minimum = 3 if method == "persistence" else 5
    reason = None
    if ambiguity:
        reason = "CONFLICTING_SAME_DATE_VALUES: Resolve the source measurements before forecasting."
    elif len(contexts) > 1:
        reason = "INCOMPATIBLE_MEASUREMENT_CONTEXTS: Specimens or laboratory methods differ."
    elif lesion_identity_required:
        reason = "LESION_IDENTITY_NOT_ESTABLISHED: Serial lesion measurements require verified same-lesion identity and calibration provenance; patient identity alone is insufficient."
    elif context_missing:
        reason = "MEASUREMENT_CONTEXT_NOT_ESTABLISHED: Comparable specimen and laboratory method must be documented for laboratory forecasting."
    elif len(series) < minimum:
        reason = f"INSUFFICIENT_REVIEWED_OBSERVATIONS: {len(series)} distinct dated values; {minimum} required for {method} backtesting."
    analysis = {"version": VERSION, "method": method, "status": "NOT_ELIGIBLE" if reason else "RESEARCH_PROTOTYPE",
                "validation_status": "NOT_EXTERNALLY_OR_CLINICALLY_VALIDATED", "prediction_interval": None,
                "interval_reason": "Calibrated prospective interval coverage has not been established.",
                "backtest": None, "forecast_date": None, "observed_change": None, "reason": reason}
    predicted = None
    mae = rmse = None
    if len(series) >= 2 and not ambiguity and len(contexts) <= 1 and not lesion_identity_required and not context_missing:
        delta = series[-1]["value"] - series[-2]["value"]
        if math.isfinite(delta):
            analysis["observed_change"] = {"absolute": delta,
                                       "from_date": series[-2]["date"], "to_date": series[-1]["date"],
                                       "clinical_direction": "INDETERMINATE"}
    if not reason:
        try:
            with np.errstate(over="raise", invalid="raise", divide="raise"):
                times = np.array([_parse_collection_time(p["date"]).timestamp() / 86400 for p in series])
                times -= times[0]
                values = np.array([p["value"] for p in series])

                def predict(t, y, at):
                    if method == "persistence":
                        return float(y[-1])
                    slope, intercept = np.polyfit(t - t[0], y, 1)
                    return float(slope * (at - t[0]) + intercept)

                start = 1 if method == "persistence" else 3
                folds = []
                for i in range(start, len(series)):
                    estimate = predict(times[:i], values[:i], times[i])
                    folds.append({"train_count": i, "target_date": series[i]["date"], "actual": float(values[i]),
                                  "predicted": estimate, "error": estimate - float(values[i]),
                                  "horizon_days": float(times[i] - times[i - 1])})
                errors = np.array([fold["error"] for fold in folds])
                mae = float(np.abs(errors).mean())
                rmse = float(np.sqrt(np.mean(errors ** 2)))
                # Extrapolation beyond the observed/backtested horizon is deliberately refused.
                max_horizon = max(fold["horizon_days"] for fold in folds)
                if horizon_days > max_horizon:
                    reason = "HORIZON_NOT_EVALUATED: Requested horizon exceeds every rolling-origin backtest horizon."
                    analysis.update(status="NOT_ELIGIBLE", reason=reason)
                else:
                    predicted = predict(times, values, times[-1] + horizon_days)
                    analysis["forecast_date"] = (_parse_collection_time(series[-1]["date"]) + timedelta(days=horizon_days)).isoformat()
                analysis["backtest"] = {"method": "EXPANDING_WINDOW_ROLLING_ORIGIN", "folds": folds, "mae": mae, "rmse": rmse,
                                        "maximum_evaluated_horizon_days": max_horizon,
                                        "coverage_validated": False, "independent_cohort": False}
                if not all(math.isfinite(v) for v in (mae, rmse, predicted if predicted is not None else 0.0)):
                    raise ValueError("Non-finite baseline output")
        except (FloatingPointError, ValueError, OverflowError, np.linalg.LinAlgError):
            predicted = mae = rmse = None
            reason = "NUMERICAL_RANGE_UNSUPPORTED: The baseline could not produce finite estimates and backtest errors."
            analysis.update(status="NOT_ELIGIBLE", reason=reason, backtest=None, forecast_date=None)
    record = ForecastRecord(case_id=case_id, target_metric=metric, unit=unit, horizon_days=horizon_days,
                            observations_count=len(series), predicted_value=predicted,
                            baseline_persistence=predicted if method == "persistence" else None,
                            baseline_linear=predicted if method == "linear" else None,
                            mae_estimate=mae, rmse_estimate=rmse, baseline_analysis={**analysis, "chronological_series": series},
                            eligibility_status=EvidenceStatus.COMPLETED if predicted is not None else EvidenceStatus.NOT_ELIGIBLE,
                            ineligibility_reason=reason,
                            notice="RESEARCH PROTOTYPE. Local backtest only; not a validated medical prognosis.")
    db.add(record)
    db.commit()
    db.refresh(record)
    return {key: getattr(record, key) for key in ("id", "case_id", "target_metric", "unit", "horizon_days", "observations_count",
            "predicted_value", "baseline_persistence", "baseline_linear", "mae_estimate", "rmse_estimate", "eligibility_status",
            "ineligibility_reason", "notice", "baseline_analysis")} | {"chronological_series": series}
