"""Longitudinal statement matching must preserve qualifiers and multiplicity."""

from datetime import datetime, timedelta, timezone

from app.models.entities import (
    Case,
    ClinicalReportStatement,
    Examination,
    Finding,
    InferenceRun,
    ModalityType,
    UploadedFile,
)
from app.services.comparison_service import ComparisonService


def _add_exam_evidence(db_session, case, exam_date, suffix, statements):
    exam = Examination(case_id=case.id, exam_date=exam_date, modality=ModalityType.REPORT)
    db_session.add(exam)
    db_session.flush()
    upload = UploadedFile(
        case_id=case.id,
        examination_id=exam.id,
        filename=f"report-{suffix}.txt",
        stored_filename=f"report-{suffix}.txt",
        file_path=f"/fixture/report-{suffix}.txt",
        file_hash=(suffix * 64)[:64],
        file_size_bytes=100,
        mime_type="text/plain",
        modality=ModalityType.REPORT,
        is_associated=True,
    )
    db_session.add(upload)
    db_session.flush()
    run = InferenceRun(
        case_id=case.id,
        file_id=upload.id,
        modality=ModalityType.REPORT,
        model_name="test-extractor",
        model_version="1",
        preprocessing_version="1",
    )
    db_session.add(run)
    db_session.flush()
    finding = Finding(
        inference_run_id=run.id,
        case_id=case.id,
        modality=ModalityType.REPORT,
        category="Clinical report",
        label="Extracted statements",
        mapping_status="NOT_MAPPED",
    )
    db_session.add(finding)
    db_session.flush()
    for statement in statements:
        db_session.add(ClinicalReportStatement(
            finding_id=finding.id,
            case_id=case.id,
            entity="Nodule",
            negation=statement.get("negation", "AFFIRMED"),
            temporality=statement.get("temporality", "CURRENT"),
            source_span=statement["source_span"],
            category="FINDING",
            certainty=statement.get("certainty", "CERTAIN"),
            experiencer="PATIENT",
            comparison=statement.get("comparison"),
            section="FINDINGS",
            anatomical_site=statement.get("anatomical_site"),
            laterality=statement.get("laterality"),
            anatomy_system="lungs",
            atlas_structure_id=statement.get("atlas_structure_id"),
        ))
    db_session.flush()
    return exam


def _case(db_session, suffix):
    case = Case(pseudonymous_id=f"CASE-STATEMENT-COMPARISON-{suffix}")
    db_session.add(case)
    db_session.flush()
    return case


def test_statement_comparison_uses_site_and_laterality_and_detects_certainty_change(db_session):
    case = _case(db_session, "QUALIFIERS")
    baseline = datetime(2026, 1, 1, tzinfo=timezone.utc)
    prior = _add_exam_evidence(db_session, case, baseline, "a", [
        {
            "source_span": "Right upper lobe nodule.",
            "anatomical_site": "upper lobe",
            "laterality": "RIGHT",
            "atlas_structure_id": "visceral.superior_lobe_of_right_lung",
        },
        {
            "source_span": "Possible left lower lobe nodule.",
            "anatomical_site": "lower lobe",
            "laterality": "LEFT",
            "atlas_structure_id": "visceral.inferior_lobe_of_left_lung",
            "certainty": "UNCERTAIN",
        },
    ])
    current = _add_exam_evidence(db_session, case, baseline + timedelta(days=30), "b", [
        {
            "source_span": "Right upper lobe nodule.",
            "anatomical_site": "upper lobe",
            "laterality": "RIGHT",
            "atlas_structure_id": "visceral.superior_lobe_of_right_lung",
        },
        {
            "source_span": "Left lower lobe nodule.",
            "anatomical_site": "lower lobe",
            "laterality": "LEFT",
            "atlas_structure_id": "visceral.inferior_lobe_of_left_lung",
            "certainty": "CERTAIN",
        },
        {
            "source_span": "Right lower lobe nodule.",
            "anatomical_site": "lower lobe",
            "laterality": "RIGHT",
            "atlas_structure_id": "visceral.inferior_lobe_of_right_lung",
        },
    ])

    result = ComparisonService.compare_examinations(db_session, case, prior.id, current.id)

    assert result["status"] == "COMPARABLE"
    assert result["semantic_comparison_blockers"] == []
    assert len(result["semantic_report_diff"]) == 2
    by_laterality = {item["identity"]["laterality"]: item for item in result["semantic_report_diff"]}
    assert by_laterality["LEFT"]["change_type"] == "DOCUMENTED_ASSERTION_CHANGED"
    assert by_laterality["LEFT"]["prior"]["certainty"] == "UNCERTAIN"
    assert by_laterality["LEFT"]["current"]["certainty"] == "CERTAIN"
    assert by_laterality["RIGHT"]["identity"]["anatomical_site"] == "lower lobe"
    assert by_laterality["RIGHT"]["change_type"] == "ADDED_IN_CURRENT_REPORT"


def test_repeated_nonidentical_statements_abstain_instead_of_overwriting(db_session):
    case = _case(db_session, "AMBIGUOUS")
    baseline = datetime(2026, 2, 1, tzinfo=timezone.utc)
    identity = {
        "anatomical_site": "upper lobe",
        "laterality": "RIGHT",
        "atlas_structure_id": "visceral.superior_lobe_of_right_lung",
    }
    prior = _add_exam_evidence(db_session, case, baseline, "c", [
        {**identity, "source_span": "Nodule described in sentence one.", "certainty": "CERTAIN"},
        {**identity, "source_span": "Nodule described in sentence two.", "certainty": "UNCERTAIN"},
    ])
    current = _add_exam_evidence(db_session, case, baseline + timedelta(days=30), "d", [
        {**identity, "source_span": "Follow-up statement A.", "certainty": "CERTAIN"},
        {**identity, "source_span": "Follow-up statement B.", "certainty": "UNCERTAIN"},
    ])

    result = ComparisonService.compare_examinations(db_session, case, prior.id, current.id)

    assert result["status"] == "NOT_COMPARABLE"
    assert result["semantic_report_diff"] == []
    assert "could not be paired safely" in result["reason"]
    assert len(result["semantic_comparison_blockers"]) == 1
    blocker = result["semantic_comparison_blockers"][0]
    assert blocker["reason"] == "REPEATED_STATEMENTS_REQUIRE_EXPLICIT_PAIRING"
    assert blocker["identity"]["laterality"] == "RIGHT"
    assert len(blocker["prior"]) == 2
    assert len(blocker["current"]) == 2
    assert len({item["statement_id"] for item in blocker["prior"] + blocker["current"]}) == 4


def test_repeated_statements_cancel_exact_rows_before_unique_pairing(db_session):
    case = _case(db_session, "DETERMINISTIC")
    baseline = datetime(2026, 3, 1, tzinfo=timezone.utc)
    identity = {
        "anatomical_site": "upper lobe",
        "laterality": "LEFT",
        "atlas_structure_id": "visceral.superior_lobe_of_left_lung",
    }
    prior = _add_exam_evidence(db_session, case, baseline, "e", [
        {**identity, "source_span": "Unchanged exact statement.", "certainty": "CERTAIN"},
        {**identity, "source_span": "Earlier uncertain statement.", "certainty": "UNCERTAIN"},
    ])
    current = _add_exam_evidence(db_session, case, baseline + timedelta(days=30), "f", [
        {**identity, "source_span": "Unchanged exact statement.", "certainty": "CERTAIN"},
        {**identity, "source_span": "Current certain statement.", "certainty": "CERTAIN"},
    ])

    result = ComparisonService.compare_examinations(db_session, case, prior.id, current.id)

    assert result["semantic_comparison_blockers"] == []
    assert len(result["semantic_report_diff"]) == 1
    change = result["semantic_report_diff"][0]
    assert change["change_type"] == "DOCUMENTED_ASSERTION_CHANGED"
    assert change["prior"]["source_span"] == "Earlier uncertain statement."
    assert change["current"]["source_span"] == "Current certain statement."
