"""Longitudinal biomarker trends from source-linked measurements.

Only documented values enter a series: measurements extracted from uploaded
documents, and laboratory results a clinician transcribed through the catalog
(labelled MANUAL_TRANSCRIPTION). A transcription that repeats an extracted value
on the same date is excluded as a duplicate. A series is defined by analyte name and
a single comparable unit: values in another unit join the series only through
a registered conversion factor (app.services.terminology.UNIT_CONVERSIONS),
and the conversion is reported. Statistics are tiered by sample size:

    n >= 2  absolute change, percent change (non-zero baseline), rate per day
    n >= 3  ordinary least-squares slope with a t-based 95% confidence interval,
            and the Theil-Sen slope as a robust alternative
    n >= 4  Mann-Kendall trend test (normal approximation, no ties correction
            beyond the standard variance adjustment)

No result is a forecast, a diagnosis, or a statement about clinical change.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
import math
from typing import Any, Optional

from scipy import stats
from sqlalchemy.orm import Session

from app.models.entities import Examination, LabInvestigationReport, MedicalMeasurement
from app.services.lab_service import LAB_CODE_ANALYTES
from app.services.terminology import ANALYTES_BY_NAME, CONVERSION_SOURCE, convert

MIN_FOR_DELTA = 2
MIN_FOR_REGRESSION = 3
MIN_FOR_MANN_KENDALL = 4

IDENTITY_REVIEW_SERIES = {"lesion_size", "nodule_size", "mass_size", "opacity_size", "cyst_size", "polyp_size", "collection_size", "calculus_size"}


def _observation_date(measurement: MedicalMeasurement, exams: dict[int, Examination]) -> tuple[Optional[date], str]:
    """Prefer the sampling date documented in the source; else the examination date."""
    if measurement.documented_date:
        try:
            return date.fromisoformat(measurement.documented_date), "DOCUMENTED_IN_SOURCE"
        except ValueError:
            pass
    exam = exams.get(measurement.examination_id) if measurement.examination_id else None
    if exam is not None:
        value = exam.exam_date
        return (value.date() if isinstance(value, datetime) else value), "EXAMINATION_DATE"
    return None, "UNDATED"


def _ols(days: list[float], values: list[float]) -> dict[str, Any]:
    n = len(days)
    result = stats.linregress(days, values)
    residual_df = n - 2
    if residual_df < 1 or not math.isfinite(result.stderr):
        return {"status": "INSUFFICIENT_OBSERVATIONS"}
    t_critical = float(stats.t.ppf(0.975, residual_df))
    slope = float(result.slope)
    half_width = t_critical * float(result.stderr)
    return {
        "status": "COMPUTED",
        "slope_per_day": slope,
        "slope_per_year": slope * 365.25,
        "slope_95ci_per_year": [(slope - half_width) * 365.25, (slope + half_width) * 365.25],
        "intercept": float(result.intercept),
        "r_squared": float(result.rvalue ** 2),
        "p_value_slope_zero": float(result.pvalue),
        "degrees_of_freedom": residual_df,
        "assumptions": "Independent observations, linear mean trend, normally distributed homoscedastic residuals. Few observations make the interval wide and the assumptions untestable.",
    }


def _theil_sen(days: list[float], values: list[float]) -> dict[str, Any]:
    slope, intercept, low, high = stats.theilslopes(values, days, alpha=0.95)
    return {
        "status": "COMPUTED",
        "slope_per_year": float(slope) * 365.25,
        "slope_95ci_per_year": [float(low) * 365.25, float(high) * 365.25],
        "assumptions": "Median of pairwise slopes; robust to single outliers. Interval from the Sen (1968) method.",
    }


def _mann_kendall(values: list[float]) -> dict[str, Any]:
    n = len(values)
    s = 0
    for i in range(n - 1):
        for j in range(i + 1, n):
            s += (values[j] > values[i]) - (values[j] < values[i])
    counts = defaultdict(int)
    for value in values:
        counts[value] += 1
    tie_term = sum(t * (t - 1) * (2 * t + 5) for t in counts.values() if t > 1)
    variance = (n * (n - 1) * (2 * n + 5) - tie_term) / 18.0
    if variance <= 0:
        return {"status": "NOT_COMPUTABLE_ALL_TIED"}
    z = (s - 1) / math.sqrt(variance) if s > 0 else (s + 1) / math.sqrt(variance) if s < 0 else 0.0
    p = 2.0 * (1.0 - stats.norm.cdf(abs(z)))
    return {
        "status": "COMPUTED",
        "s_statistic": s,
        "z": z,
        "p_value_two_sided": float(p),
        "kendall_tau": float(stats.kendalltau(range(n), values).statistic),
        "assumptions": "Monotonic trend test on serially independent observations; the normal approximation is coarse for small n.",
    }


def _extracted_observations(db: Session, case_id: int) -> list[dict[str, Any]]:
    """Measurements extracted from uploaded documents, with their source spans."""
    rows = (
        db.query(MedicalMeasurement)
        .filter(MedicalMeasurement.case_id == case_id)
        .order_by(MedicalMeasurement.id.asc())
        .all()
    )
    exams = {exam.id: exam for exam in db.query(Examination).filter(Examination.case_id == case_id).all()}
    observations = []
    for row in rows:
        observed_on, date_source = _observation_date(row, exams)
        observations.append({
            "observation_id": f"m{row.id}",
            "source_type": "DOCUMENT_EXTRACTION",
            "measurement_id": row.id,
            "lab_report_id": None,
            "name": row.name,
            "display_name": row.display_name,
            "value": row.value,
            "result_operator": row.result_operator or "=",
            "unit": row.unit,
            "date": observed_on,
            "date_source": date_source,
            "source_file_id": row.source_file_id,
            "examination_id": row.examination_id,
            "source_span": row.source_span,
            "reference_low": row.reference_low,
            "reference_high": row.reference_high,
            "documented_flag": row.documented_flag,
            "anatomy_system": row.anatomy_system,
            "association": row.association,
            "canonical_code": row.canonical_code,
            "specimen": row.specimen or "NOT_DOCUMENTED",
            "laboratory_method": row.laboratory_method or "NOT_DOCUMENTED",
        })
    return observations


def _transcribed_observations(db: Session, case_id: int) -> list[dict[str, Any]]:
    """Quantitative results a clinician recorded through the laboratory catalog."""
    reports = (
        db.query(LabInvestigationReport)
        .filter(LabInvestigationReport.case_id == case_id)
        .order_by(LabInvestigationReport.id.asc())
        .all()
    )
    observations = []
    for report in reports:
        payload = report.test_results_json if isinstance(report.test_results_json, dict) else {"results": report.test_results_json or []}
        observed_on = None
        if payload.get("collection_date"):
            try:
                observed_on = date.fromisoformat(payload["collection_date"])
            except ValueError:
                observed_on = None
        for result in payload.get("results", []):
            name = LAB_CODE_ANALYTES.get(result.get("code", ""))
            value = result.get("result_value")
            if name is None or not isinstance(value, (int, float)):
                continue
            analyte = ANALYTES_BY_NAME.get(name)
            # Only an interval the laboratory printed is a documented interval; catalog defaults are not.
            documented_interval = result.get("reference_source") == "REPORTING_LABORATORY"
            observations.append({
                "observation_id": f"l{report.id}:{result['code']}",
                "source_type": "MANUAL_TRANSCRIPTION",
                "measurement_id": None,
                "lab_report_id": report.id,
                "name": name,
                "display_name": analyte.display if analyte else result.get("test_name", name),
                "value": float(value),
                "result_operator": result.get("result_operator", "="),
                "unit": result.get("unit", ""),
                "date": observed_on,
                "date_source": "DOCUMENTED_COLLECTION_DATE" if observed_on else "UNDATED",
                "source_file_id": payload.get("source_file_id"),
                "examination_id": None,
                "source_span": f"{result.get('test_name', name)}: {value:g} {result.get('unit', '')}".strip(),
                "reference_low": result.get("ref_low") if documented_interval else None,
                "reference_high": result.get("ref_high") if documented_interval else None,
                "documented_flag": None,
                "anatomy_system": analyte.system if analyte else None,
                "association": analyte.association if analyte else None,
                "canonical_code": None,
                "specimen": report.sample_type or "NOT_DOCUMENTED",
                "laboratory_method": payload.get("laboratory_method") or "NOT_DOCUMENTED",
            })
    return observations


def _duplicate_of(candidate: dict[str, Any], value: float, extracted: list[dict[str, Any]]) -> Optional[str]:
    """An extracted point with the same analyte, date and value is the same observation."""
    for point in extracted:
        if point["date"] == candidate["date"] and math.isclose(point["value"], value, rel_tol=1e-9, abs_tol=1e-12):
            return point["observation_id"]
    return None


def build_series(db: Session, case_id: int) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for observation in _extracted_observations(db, case_id) + _transcribed_observations(db, case_id):
        grouped[observation["name"]].append(observation)

    series_list: list[dict[str, Any]] = []
    for name, items in sorted(grouped.items()):
        unit_counts: dict[str, int] = defaultdict(int)
        for item in items:
            unit_counts[item["unit"]] += 1
        target_unit = max(unit_counts, key=lambda unit: (unit_counts[unit], unit))
        points, excluded = [], []
        for item in items:
            exclusion = {"observation_id": item["observation_id"], "measurement_id": item["measurement_id"], "lab_report_id": item["lab_report_id"]}
            if item["result_operator"] != "=":
                excluded.append({**exclusion, "reason": f"CENSORED_RESULT_{item['result_operator']}"})
                continue
            converted = convert(name, item["value"], item["unit"], target_unit)
            if converted is None:
                excluded.append({**exclusion, "reason": f"NO_REGISTERED_CONVERSION_{item['unit']}_TO_{target_unit}"})
                continue
            if item["date"] is None:
                excluded.append({**exclusion, "reason": "UNDATED_OBSERVATION"})
                continue
            point = {
                "observation_id": item["observation_id"],
                "source_type": item["source_type"],
                "measurement_id": item["measurement_id"],
                "lab_report_id": item["lab_report_id"],
                "date": item["date"].isoformat(),
                "date_source": item["date_source"],
                "value": converted,
                "documented_value": item["value"],
                "result_operator": item["result_operator"],
                "documented_unit": item["unit"],
                "unit_converted": item["unit"] != target_unit,
                "source_file_id": item["source_file_id"],
                "examination_id": item["examination_id"],
                "source_span": item["source_span"],
                "reference_low": item["reference_low"],
                "reference_high": item["reference_high"],
                "documented_flag": item["documented_flag"],
                "specimen": item["specimen"],
                "laboratory_method": item["laboratory_method"],
            }
            if item["source_type"] == "MANUAL_TRANSCRIPTION":
                extracted = [other for other in points if other["source_type"] == "DOCUMENT_EXTRACTION"]
                duplicate = _duplicate_of(point, converted, extracted)
                if duplicate:
                    excluded.append({**exclusion, "reason": f"DUPLICATE_OF_{duplicate.upper()}"})
                    continue
            points.append(point)
        points.sort(key=lambda point: (point["date"], point["observation_id"]))
        analyte = ANALYTES_BY_NAME.get(name)
        first = items[0]
        comparability_blockers: list[str] = []
        if analyte and analyte.association != "PHYSIOLOGICAL_SIGNAL" and points:
            specimens = {str(point["specimen"]).strip().casefold() for point in points}
            methods = {str(point["laboratory_method"]).strip().casefold() for point in points}
            if "not_documented" in specimens:
                comparability_blockers.append("SPECIMEN_NOT_DOCUMENTED")
            elif len(specimens) > 1:
                comparability_blockers.append("SPECIMEN_MISMATCH")
            if "not_documented" in methods:
                comparability_blockers.append("LABORATORY_METHOD_NOT_DOCUMENTED")
            elif len(methods) > 1:
                comparability_blockers.append("LABORATORY_METHOD_MISMATCH")
        analysis = analyse_points(points)
        if comparability_blockers:
            analysis = {
                "status": "COMPARABILITY_NOT_ESTABLISHED",
                "reason": "Laboratory series require the same documented specimen and method before arithmetic trends are computed.",
                "blockers": comparability_blockers,
                "n": len(points),
                "distinct_dates": len({point["date"] for point in points}),
                "interpretation": None,
            }
        series = {
            "name": name,
            "display_name": first["display_name"],
            "unit": target_unit,
            "anatomy_system": first["anatomy_system"] or (analyte.system if analyte else None),
            "association": first["association"] or (analyte.association if analyte else None),
            "canonical_code": next((item["canonical_code"] for item in items if item["canonical_code"]), None),
            "source_types": sorted({point["source_type"] for point in points}),
            "points": points,
            "excluded": excluded,
            "conversions": sorted({f"{point['documented_unit']} -> {target_unit}" for point in points if point["unit_converted"]}),
            "conversion_source": CONVERSION_SOURCE if any(point["unit_converted"] for point in points) else None,
            "identity_review_required": name in IDENTITY_REVIEW_SERIES,
            "comparability_blockers": comparability_blockers,
            "analysis": analysis,
        }
        series_list.append(series)
    return series_list


def analyse_points(points: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(points)
    distinct_dates = len({point["date"] for point in points})
    result: dict[str, Any] = {"n": n, "distinct_dates": distinct_dates}
    if n < MIN_FOR_DELTA or distinct_dates < 2:
        result["status"] = "INSUFFICIENT_OBSERVATIONS"
        result["reason"] = "At least two dated observations on different dates are required."
        return result
    first, last = points[0], points[-1]
    first_day = date.fromisoformat(first["date"])
    interval_days = (date.fromisoformat(last["date"]) - first_day).days
    delta = last["value"] - first["value"]
    result.update({
        "status": "COMPUTED",
        "first": {"date": first["date"], "value": first["value"]},
        "last": {"date": last["date"], "value": last["value"]},
        "absolute_change": delta,
        "percent_change": None if first["value"] == 0 else 100.0 * delta / abs(first["value"]),
        "percent_change_status": "UNDEFINED_ZERO_BASELINE" if first["value"] == 0 else "COMPUTED",
        "interval_days": interval_days,
        "rate_per_day": delta / interval_days if interval_days else None,
        "rate_per_year": delta / interval_days * 365.25 if interval_days else None,
        "formulae": {
            "absolute_change": "x_last - x_first",
            "percent_change": "100 * (x_last - x_first) / |x_first|",
            "rate": "(x_last - x_first) / (t_last - t_first)",
        },
    })
    days = [float((date.fromisoformat(point["date"]) - first_day).days) for point in points]
    values = [float(point["value"]) for point in points]
    if n >= MIN_FOR_REGRESSION and distinct_dates >= MIN_FOR_REGRESSION:
        result["ols"] = _ols(days, values)
        result["theil_sen"] = _theil_sen(days, values)
    else:
        result["ols"] = {"status": "INSUFFICIENT_OBSERVATIONS", "required": MIN_FOR_REGRESSION}
        result["theil_sen"] = {"status": "INSUFFICIENT_OBSERVATIONS", "required": MIN_FOR_REGRESSION}
    result["mann_kendall"] = _mann_kendall(values) if n >= MIN_FOR_MANN_KENDALL else {"status": "INSUFFICIENT_OBSERVATIONS", "required": MIN_FOR_MANN_KENDALL}
    result["time_series_models"] = {
        "status": "NOT_APPLICABLE",
        "reason": "ARIMA, state-space and change-point models are not fitted to individual-patient series of this length.",
    }
    result["interpretation"] = None
    return result
