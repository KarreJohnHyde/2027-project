"""Validated clinical equations evaluated only on documented inputs.

CKD-EPI 2021 creatinine equation (race-free):

    eGFR = 142 * min(Scr/k, 1)^a * max(Scr/k, 1)^-1.200 * 0.9938^Age * 1.012 [female]
    k = 0.7 (female), 0.9 (male); a = -0.241 (female), -0.302 (male)

Reference: Inker LA, Eneanya ND, Coresh J, et al. New creatinine- and
cystatin C-based equations to estimate GFR without race. N Engl J Med.
2021;385(19):1737-1749.

Every input must be documented in the case's own sources. If any input is
missing, ambiguous or conflicting, the result is INSUFFICIENT_EVIDENCE and no
number is returned.
"""

from __future__ import annotations

from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import DocumentedAttribute, MedicalMeasurement
from app.services.terminology import convert

CKD_EPI_2021 = {
    "equation_id": "CKD_EPI_2021_CREATININE",
    "display": "CKD-EPI 2021 creatinine equation (race-free)",
    "citation": "Inker LA, et al. N Engl J Med. 2021;385(19):1737-1749.",
    "unit": "mL/min/1.73m²",
    "population": "Adults (age >= 18) with stable serum creatinine.",
    "caveats": [
        "Estimated, not measured, GFR.",
        "Not valid when creatinine is not at steady state (for example acute kidney injury).",
        "Assumes an IDMS-traceable creatinine assay; the assay cannot be verified from report text.",
        "Extremes of muscle mass, amputation or pregnancy reduce accuracy.",
    ],
}


def ckd_epi_2021(creatinine_mg_dl: float, age_years: float, sex: str) -> float:
    female = sex == "female"
    kappa = 0.7 if female else 0.9
    alpha = -0.241 if female else -0.302
    ratio = creatinine_mg_dl / kappa
    value = 142.0 * min(ratio, 1.0) ** alpha * max(ratio, 1.0) ** -1.200 * 0.9938 ** age_years
    return value * 1.012 if female else value


def _attribute(rows: list[DocumentedAttribute], name: str, source_file_id: Optional[int] = None) -> list[DocumentedAttribute]:
    return [row for row in rows if row.name == name and (source_file_id is None or row.source_file_id == source_file_id)]


def egfr_for_case(db: Session, case_id: int) -> dict[str, Any]:
    creatinine = (
        db.query(MedicalMeasurement)
        .filter(MedicalMeasurement.case_id == case_id, MedicalMeasurement.name == "creatinine")
        .order_by(MedicalMeasurement.id.asc())
        .all()
    )
    attributes = db.query(DocumentedAttribute).filter(DocumentedAttribute.case_id == case_id).all()
    sexes = {row.value_text for row in _attribute(attributes, "sex") if row.value_text}
    results = []
    for measurement in creatinine:
        missing: list[str] = []
        if (measurement.result_operator or "=") != "=":
            missing.append("CREATININE_IS_CENSORED_NOT_AN_EXACT_VALUE")
        scr = convert("creatinine", measurement.value, measurement.unit, "mg/dL")
        if scr is None:
            missing.append(f"CREATININE_UNIT_NOT_CONVERTIBLE ({measurement.unit})")
        same_source_age = [row for row in _attribute(attributes, "age_years", measurement.source_file_id) if row.value_number is not None]
        any_age = [row for row in _attribute(attributes, "age_years") if row.value_number is not None]
        age_row = same_source_age[0] if same_source_age else (any_age[0] if len({row.value_number for row in any_age}) == 1 else None)
        if age_row is None:
            missing.append("AGE_NOT_DOCUMENTED_OR_CONFLICTING" if any_age else "AGE_NOT_DOCUMENTED")
        elif age_row.value_number < 18:
            missing.append("AGE_BELOW_EQUATION_POPULATION")
        if len(sexes) != 1:
            missing.append("SEX_CONFLICTING" if sexes else "SEX_NOT_DOCUMENTED")
        record: dict[str, Any] = {
            "creatinine_measurement_id": measurement.id,
            "source_file_id": measurement.source_file_id,
            "documented_creatinine": {"value": measurement.value, "unit": measurement.unit, "source_span": measurement.source_span},
            "documented_date": measurement.documented_date,
        }
        if missing:
            record.update({"status": "INSUFFICIENT_EVIDENCE", "missing_or_invalid_inputs": missing, "value": None})
        else:
            sex = next(iter(sexes))
            record.update({
                "status": "COMPUTED_FROM_DOCUMENTED_INPUTS",
                "value": round(ckd_epi_2021(scr, age_row.value_number, sex), 1),
                "unit": CKD_EPI_2021["unit"],
                "inputs": {
                    "creatinine_mg_dl": round(scr, 4),
                    "age_years": age_row.value_number,
                    "age_source": {"source_file_id": age_row.source_file_id, "source_span": age_row.source_span, "same_source_as_creatinine": bool(same_source_age)},
                    "sex": sex,
                },
                "interpretation": None,
            })
        results.append(record)
    return {
        "equation": CKD_EPI_2021,
        "status": "NO_CREATININE_DOCUMENTED" if not creatinine else ("COMPUTED" if any(item["status"].startswith("COMPUTED") for item in results) else "INSUFFICIENT_EVIDENCE"),
        "results": results,
        "notice": "Calculated research value from documented inputs; review against the reporting laboratory's own eGFR.",
    }
