"""Evidence-gated longitudinal comparison service.

The current schema stores examinations but does not bind extracted report
statements or numeric measurements to those examinations. Until that provenance
link exists, the service must not manufacture clinical deltas, registration
errors, or L2 anatomical states.
"""

from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    Case,
    ClinicalReportStatement,
    Examination,
    Finding,
    InferenceRun,
    MedicalMeasurement,
    ModalityType,
    UploadedFile,
)
from app.services.terminology import ANALYTES_BY_NAME


# Only documented qualifiers participate in statement identity. A missing site
# or laterality is intentionally distinct from a documented one; the comparison
# service must not infer that two incompletely localized findings are equivalent.
STATEMENT_IDENTITY_FIELDS = (
    "entity",
    "category",
    "anatomical_site",
    "laterality",
    "anatomy_system",
    "atlas_structure_id",
    "experiencer",
    "section",
)


def _statement_identity(row: ClinicalReportStatement) -> tuple[Any, ...]:
    return tuple(getattr(row, field) for field in STATEMENT_IDENTITY_FIELDS)


def _statement_identity_payload(identity: tuple[Any, ...]) -> dict[str, Any]:
    return dict(zip(STATEMENT_IDENTITY_FIELDS, identity))


def _statement_payload(row: ClinicalReportStatement) -> dict[str, Any]:
    return {
        "statement_id": row.id,
        "assertion": row.negation,
        "temporality": row.temporality,
        "certainty": row.certainty,
        "comparison": row.comparison,
        "source_span": row.source_span,
        "source_file_id": row.finding.inference_run.file_id,
    }


def _statement_fingerprint(statement: dict[str, Any]) -> tuple[Any, ...]:
    """Fields that must match before two statement rows cancel exactly.

    IDs and source-file IDs are provenance, not semantic equivalence. Source
    text remains part of the fingerprint so differently worded statements are
    never silently declared equal.
    """

    return tuple(
        statement[field]
        for field in ("assertion", "temporality", "certainty", "comparison", "source_span")
    )


def _cancel_exact_statement_matches(
    prior: list[dict[str, Any]],
    current: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Deterministically cancel one current row for each exact prior row."""

    unmatched_current = list(current)
    unmatched_prior: list[dict[str, Any]] = []
    for prior_statement in prior:
        fingerprint = _statement_fingerprint(prior_statement)
        match_index = next(
            (
                index
                for index, current_statement in enumerate(unmatched_current)
                if _statement_fingerprint(current_statement) == fingerprint
            ),
            None,
        )
        if match_index is None:
            unmatched_prior.append(prior_statement)
        else:
            unmatched_current.pop(match_index)
    return unmatched_prior, unmatched_current


class ComparisonService:
    """Resolve a same-case date pair and report only evidence-supported readiness."""

    @staticmethod
    def compare_examinations(
        db: Session,
        case: Case,
        prior_exam_id: Optional[int] = None,
        current_exam_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        exams = (
            db.query(Examination)
            .filter(Examination.case_id == case.id)
            .order_by(Examination.exam_date.asc())
            .all()
        )
        if len(exams) < 2:
            return {
                "status": "NOT_COMPARABLE",
                "reason": "At least two dated examinations are required for longitudinal comparison.",
                "case_id": case.id,
                "case_pseudonym": case.pseudonymous_id,
                "examinations_count": len(exams),
            }

        prior_exam = next((exam for exam in exams if exam.id == prior_exam_id), None) if prior_exam_id else exams[0]
        current_exam = next((exam for exam in exams if exam.id == current_exam_id), None) if current_exam_id else exams[-1]
        if not prior_exam or not current_exam:
            return {
                "status": "ERROR",
                "reason": "Specified examination IDs could not be resolved for this case.",
                "case_id": case.id,
            }
        if prior_exam.id == current_exam.id or prior_exam.exam_date >= current_exam.exam_date:
            return {
                "status": "NOT_COMPARABLE",
                "reason": "Prior and current examinations must be distinct and chronologically ordered.",
                "case_id": case.id,
            }

        prior_images = db.query(UploadedFile).filter(
            UploadedFile.case_id == case.id,
            UploadedFile.examination_id == prior_exam.id,
            UploadedFile.modality == ModalityType.IMAGE,
            UploadedFile.is_associated.is_(True),
        ).count()
        current_images = db.query(UploadedFile).filter(
            UploadedFile.case_id == case.id,
            UploadedFile.examination_id == current_exam.id,
            UploadedFile.modality == ModalityType.IMAGE,
            UploadedFile.is_associated.is_(True),
        ).count()

        def statement_snapshot(examination_id: int) -> dict[tuple[Any, ...], list[dict[str, Any]]]:
            rows = (
                db.query(ClinicalReportStatement)
                .join(Finding, ClinicalReportStatement.finding_id == Finding.id)
                .join(InferenceRun, Finding.inference_run_id == InferenceRun.id)
                .join(UploadedFile, InferenceRun.file_id == UploadedFile.id)
                .filter(
                    UploadedFile.case_id == case.id,
                    UploadedFile.examination_id == examination_id,
                    UploadedFile.is_associated.is_(True),
                )
                .order_by(ClinicalReportStatement.id.asc())
                .all()
            )
            snapshot: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
            for row in rows:
                snapshot.setdefault(_statement_identity(row), []).append(_statement_payload(row))
            return snapshot

        prior_statements = statement_snapshot(prior_exam.id)
        current_statements = statement_snapshot(current_exam.id)
        semantic_diff = []
        semantic_comparison_blockers = []
        statement_identities = set(prior_statements) | set(current_statements)
        for identity in sorted(statement_identities, key=lambda value: tuple("" if item is None else str(item) for item in value)):
            prior_rows = prior_statements.get(identity, [])
            current_rows = current_statements.get(identity, [])
            unmatched_prior, unmatched_current = _cancel_exact_statement_matches(prior_rows, current_rows)
            if not unmatched_prior and not unmatched_current:
                continue

            identity_payload = _statement_identity_payload(identity)
            entity = identity_payload["entity"]
            # Multiple non-identical rows on both sides cannot be paired without
            # inventing equivalence. Preserve every row and abstain for this
            # composite identity instead of choosing the last database record.
            if len(unmatched_prior) > 1 or len(unmatched_current) > 1:
                if unmatched_prior and unmatched_current:
                    semantic_comparison_blockers.append({
                        "entity": entity,
                        "identity": identity_payload,
                        "reason": "REPEATED_STATEMENTS_REQUIRE_EXPLICIT_PAIRING",
                        "prior": unmatched_prior,
                        "current": unmatched_current,
                    })
                    continue

            if not unmatched_prior:
                for current_value in unmatched_current:
                    semantic_diff.append({
                        "entity": entity,
                        "identity": identity_payload,
                        "change_type": "ADDED_IN_CURRENT_REPORT",
                        "prior": None,
                        "current": current_value,
                        "interpretation": None,
                    })
                continue
            if not unmatched_current:
                for prior_value in unmatched_prior:
                    semantic_diff.append({
                        "entity": entity,
                        "identity": identity_payload,
                        "change_type": "NOT_PRESENT_IN_CURRENT_REPORT",
                        "prior": prior_value,
                        "current": None,
                        "interpretation": None,
                    })
                continue

            # The only remaining safe paired case is exactly one documented row
            # on each side of the same full composite identity.
            prior_value = unmatched_prior[0]
            current_value = unmatched_current[0]
            if (
                prior_value["assertion"] != current_value["assertion"]
                or prior_value["temporality"] != current_value["temporality"]
                or prior_value["certainty"] != current_value["certainty"]
                or prior_value["comparison"] != current_value["comparison"]
            ):
                change_type = "DOCUMENTED_ASSERTION_CHANGED"
            else:
                change_type = "DOCUMENTED_SOURCE_STATEMENT_CHANGED"
            semantic_diff.append({
                "entity": entity,
                "identity": identity_payload,
                "change_type": change_type,
                "prior": prior_value,
                "current": current_value,
                "interpretation": None,
            })

        def measurement_snapshot(examination_id: int) -> dict[tuple[str, str], list[MedicalMeasurement]]:
            rows = (
                db.query(MedicalMeasurement)
                .filter(
                    MedicalMeasurement.case_id == case.id,
                    MedicalMeasurement.examination_id == examination_id,
                )
                .order_by(MedicalMeasurement.id.asc())
                .all()
            )
            snapshot: dict[tuple[str, str], list[MedicalMeasurement]] = {}
            for row in rows:
                snapshot.setdefault((row.name, row.unit), []).append(row)
            return snapshot

        prior_measurements = measurement_snapshot(prior_exam.id)
        current_measurements = measurement_snapshot(current_exam.id)
        numeric_deltas = []
        numeric_comparison_blockers = []
        for key in sorted(set(prior_measurements) & set(current_measurements)):
            prior_rows = prior_measurements[key]
            current_rows = current_measurements[key]
            blocker = {"name": key[0], "unit": key[1], "prior_measurement_ids": [row.id for row in prior_rows], "current_measurement_ids": [row.id for row in current_rows]}
            if len(prior_rows) != 1 or len(current_rows) != 1:
                numeric_comparison_blockers.append({**blocker, "reason": "REPEATED_MEASUREMENTS_REQUIRE_EXPLICIT_PAIRING"})
                continue
            prior_value, current_value = prior_rows[0], current_rows[0]
            if (prior_value.result_operator or "=") != "=" or (current_value.result_operator or "=") != "=":
                numeric_comparison_blockers.append({**blocker, "reason": "CENSORED_RESULT_IS_NOT_AN_EXACT_VALUE"})
                continue
            analyte = ANALYTES_BY_NAME.get(prior_value.name)
            if analyte and analyte.association != "PHYSIOLOGICAL_SIGNAL":
                for field, reason in (("specimen", "SPECIMEN_COMPARABILITY_NOT_ESTABLISHED"), ("laboratory_method", "METHOD_COMPARABILITY_NOT_ESTABLISHED")):
                    prior_context = getattr(prior_value, field) or "NOT_DOCUMENTED"
                    current_context = getattr(current_value, field) or "NOT_DOCUMENTED"
                    if "NOT_DOCUMENTED" in {prior_context.upper(), current_context.upper()} or prior_context.casefold() != current_context.casefold():
                        numeric_comparison_blockers.append({**blocker, "reason": reason, "prior": prior_context, "current": current_context})
                        break
                else:
                    pass
                if numeric_comparison_blockers and numeric_comparison_blockers[-1].get("name") == key[0] and numeric_comparison_blockers[-1].get("unit") == key[1]:
                    continue
            delta = current_value.value - prior_value.value
            percent_change = None if prior_value.value == 0 else (delta / abs(prior_value.value)) * 100.0
            numeric_deltas.append({
                "name": prior_value.name,
                "display_name": prior_value.display_name,
                "unit": prior_value.unit,
                "prior": {
                    "measurement_id": prior_value.id,
                    "value": prior_value.value,
                    "source_file_id": prior_value.source_file_id,
                    "source_span": prior_value.source_span,
                },
                "current": {
                    "measurement_id": current_value.id,
                    "value": current_value.value,
                    "source_file_id": current_value.source_file_id,
                    "source_span": current_value.source_span,
                },
                "absolute_delta": round(delta, 6),
                "percent_change": None if percent_change is None else round(percent_change, 3),
                "interpretation": None,
                "review_status": "PENDING_HUMAN_REVIEW",
            })

        is_comparable = bool(semantic_diff or numeric_deltas)
        has_blockers = bool(semantic_comparison_blockers or numeric_comparison_blockers)

        return {
            "status": "COMPARABLE" if is_comparable else "NOT_COMPARABLE",
            "reason": (
                "Source-linked report statements and/or unit-compatible measurements were compared without clinical interpretation."
                if is_comparable
                else (
                    "Evidence was present but could not be paired safely; see the comparison blockers. No clinical change was inferred."
                    if has_blockers
                    else "The selected examinations have no source-linked statement changes or unit-compatible numeric measurements. No clinical change was inferred."
                )
            ),
            "case_id": case.id,
            "case_pseudonym": case.pseudonymous_id,
            "prior_examination": {
                "id": prior_exam.id,
                "date": prior_exam.exam_date.isoformat(),
                "modality": prior_exam.modality.value,
            },
            "current_examination": {
                "id": current_exam.id,
                "date": current_exam.exam_date.isoformat(),
                "modality": current_exam.modality.value,
            },
            "interval_days": (current_exam.exam_date - prior_exam.exam_date).days,
            "semantic_report_diff": semantic_diff,
            "semantic_comparison_blockers": semantic_comparison_blockers,
            "numeric_deltas": numeric_deltas,
            "numeric_comparison_blockers": numeric_comparison_blockers,
            "image_comparison": {
                "status": "NOT_RUN",
                "is_comparable": False,
                "prior_associated_image_count": prior_images,
                "current_associated_image_count": current_images,
                "reason": "No validated image-registration result links this examination pair.",
            },
            "twin_state_delta": {
                "status": "MAPPING_UNSUPPORTED",
                "representation_level": "L1",
                "reason": "No held-out landmark registration supports an L2 anatomical comparison.",
            },
            "notice": (
                "Deltas describe documented source values only. No diagnosis, progression, resolution, causality, "
                "reference-range interpretation, or anatomical localization was generated."
            ),
        }
