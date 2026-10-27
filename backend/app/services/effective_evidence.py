"""Effective (reviewed) view of extracted evidence.

Extracted statements and measurements are immutable. A reviewer proposes a typed correction
(HumanReview.correction_payload); a second, independent verified reviewer approves or rejects
it (CorrectionDecision). Only approved corrections are applied, and only in this derived view:
each record carries the original values, the effective values and its correction state.

States: ORIGINAL_IMMUTABLE (no correction), CORRECTION_PROPOSED (awaiting a decision),
CORRECTION_REJECTED, CORRECTION_APPLIED_TO_EFFECTIVE_VIEW, REMOVED_IN_EFFECTIVE_VIEW. When
several approved corrections target one item, the most recently decided one applies.
"""

from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

from sqlalchemy.orm import Session

from app.models.entities import Finding, HumanReview

MEASUREMENT_FIELDS = {
    "corrected_display_name": "display_name",
    "corrected_value": "value",
    "corrected_result_operator": "result_operator",
    "corrected_unit": "unit",
    "corrected_reference_low": "reference_low",
    "corrected_reference_high": "reference_high",
    "corrected_specimen": "specimen",
    "corrected_laboratory_method": "laboratory_method",
}
STATEMENT_FIELDS = {
    "corrected_entity": "entity",
    "corrected_assertion": "negation",
    "corrected_temporality": "temporality",
    "corrected_certainty": "certainty",
    "corrected_anatomical_site": "anatomical_site",
    "corrected_laterality": "laterality",
}


def correction_index(db: Session, case_id: int) -> tuple[dict[int, list[dict]], dict[int, list[dict]]]:
    """Per measurement id and per statement id: every correction proposed for it, with its decision."""
    reviews = (
        db.query(HumanReview)
        .join(Finding, Finding.id == HumanReview.finding_id)
        .filter(Finding.case_id == case_id, HumanReview.correction_payload.isnot(None))
        .order_by(HumanReview.reviewed_at.asc(), HumanReview.id.asc())
        .all()
    )
    measurements: dict[int, list[dict]] = defaultdict(list)
    statements: dict[int, list[dict]] = defaultdict(list)
    for review in reviews:
        decision = review.decision
        state = "CORRECTION_PROPOSED" if decision is None else (
            "CORRECTION_APPROVED" if decision.decision == "APPROVED" else "CORRECTION_REJECTED"
        )
        common = {
            "review_id": review.id,
            "proposed_by_id": review.reviewer_id,
            "proposed_at": review.reviewed_at.isoformat(),
            "state": state,
            "decided_by_id": decision.decided_by_id if decision else None,
            "decided_at": decision.decided_at.isoformat() if decision else None,
        }
        payload = review.correction_payload or {}
        for item in payload.get("measurement_corrections", []):
            measurements[item["target_measurement_id"]].append({**common, "correction": item})
        for item in payload.get("entity_corrections", []):
            statements[item["target_statement_id"]].append({**common, "correction": item})
    return measurements, statements


def effective_record(original: dict[str, Any], entries: list[dict], fields: dict[str, str]) -> dict[str, Any]:
    """Original values, effective values after the latest approved correction, and the state."""
    approved = [entry for entry in entries if entry["state"] == "CORRECTION_APPROVED"]
    effective = {target: original.get(target) for target in fields.values()}
    applied: Optional[dict] = None
    if approved:
        applied = max(approved, key=lambda entry: entry["decided_at"] or "")
        correction = applied["correction"]
        if correction["action"] == "REMOVE":
            state = "REMOVED_IN_EFFECTIVE_VIEW"
        else:
            state = "CORRECTION_APPLIED_TO_EFFECTIVE_VIEW"
            for source, target in fields.items():
                if correction.get(source) is not None:
                    effective[target] = correction[source]
    elif any(entry["state"] == "CORRECTION_PROPOSED" for entry in entries):
        state = "CORRECTION_PROPOSED"
    elif entries:
        state = "CORRECTION_REJECTED"
    else:
        state = "ORIGINAL_IMMUTABLE"
    return {
        "correction_state": state,
        "original": {target: original.get(target) for target in fields.values()},
        "effective": effective,
        "applied_review_id": applied["review_id"] if applied else None,
        "corrections": entries,
    }


def approved_measurement_overrides(db: Session, case_id: int) -> dict[int, dict[str, Any]]:
    """Measurement id -> {"removed": bool, "fields": {...}, "review_id": int} for approved corrections."""
    measurements, _ = correction_index(db, case_id)
    overrides: dict[int, dict[str, Any]] = {}
    for measurement_id, entries in measurements.items():
        approved = [entry for entry in entries if entry["state"] == "CORRECTION_APPROVED"]
        if not approved:
            continue
        latest = max(approved, key=lambda entry: entry["decided_at"] or "")
        correction = latest["correction"]
        overrides[measurement_id] = {
            "removed": correction["action"] == "REMOVE",
            "fields": {target: correction[source] for source, target in MEASUREMENT_FIELDS.items() if correction.get(source) is not None},
            "review_id": latest["review_id"],
        }
    return overrides
