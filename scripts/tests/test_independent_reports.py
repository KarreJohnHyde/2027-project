"""Synthetic software controls only; no independent real clinical gold supplied."""
import copy
import io
import json
from pathlib import Path
import sys
import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
from scripts import evaluate_independent_reports as runner
from scripts.review_document_annotations import annotation_digest


def write(path, value):
    path.write_text(json.dumps(value), encoding="utf-8")


def field(analyte="glucose", value="5.2", box=None):
    return {"analyte": analyte, "value": value, "value_state": "READABLE", "unit": "mmol/L", "specimen": "Serum",
        "collection_date": "2026-11-01", "report_date": "2026-11-02", "reference_interval": None, "comparator": None,
        "assertion": "CERTAIN", "negation": "AFFIRMED", "temporality": "CURRENT", "source_bbox": box or [10, 10, 180, 60]}


@pytest.fixture
def bundle(tmp_path):
    from app.services.ocr import render_pdf_page
    pdf_path = tmp_path / "synthetic-report.pdf"
    Image.new("RGB", (144, 144), "white").save(pdf_path, "PDF")
    raw = pdf_path.read_bytes()
    image = render_pdf_page(raw, 0, 150).convert("RGB")
    image_path = tmp_path / "source-page.png"; image.save(image_path)
    text = "Glucose 5.2 mmol/L\nNo pleural effusion."
    start = text.index("pleural effusion")
    page = {"document_id": "synthetic-control-only", "page": 1, "source_image_sha256": runner.digest(image_path.read_bytes()),
        "width": image.width, "height": image.height, "deidentified": True, "permission_scope": "Synthetic unit-test control; no clinical report or permission asserted",
        "evidence_type": "SYNTHETIC", "readability": "READABLE", "gold_text": text, "unreadable_reason": None,
        "fields": [field(), field("hemoglobin", "12.4", [10, 110, 180, 150])],
        "entities": [{"start": start, "end": start + len("pleural effusion"), "label": "FINDING", "assertion": "CERTAIN", "negation": "NEGATED", "temporality": "CURRENT", "source_bbox": [10, 200, 180, 240]}],
        "review": {"status": "FINALIZED", "annotator_id": "synthetic-test-annotator", "reviewer_id": "synthetic-test-reviewer",
            "independently_transcribed": True, "critical_fields_checked": True, "reviewed_at": "2026-11-13T00:00:00+00:00"}}
    page["review"]["reviewed_content_sha256"] = annotation_digest(page)
    ann_path = tmp_path / "annotations.json"; write(ann_path, {"schema_version": "medtwin.review-document-annotation.v1", "pages": [page]})
    inventory = {"schema_version": "medtwin.independent-full-report-inventory.v1", "reference_provenance": {
        "independently_checked_full_reports": True, "target_annotations_complete": True, "created_without_system_predictions": True, "used_for_training_or_tuning": False,
        "predictions_visible_to_annotators": False, "evaluation_split": "HELD_OUT_UNEXPOSED"}, "documents": [{
            "document_id": page["document_id"], "source_pdf_path": pdf_path.name, "source_pdf_sha256": runner.digest(raw), "page_count": 1,
            "rendering": {"engine": "pypdfium2", "dpi": 150, "crop": "FULL_PAGE", "rotation_degrees": 0},
            "pages": [{"page": 1, "source_image_path": image_path.name, "source_image_sha256": page["source_image_sha256"], "width": image.width, "height": image.height}]}]}
    inv_path = tmp_path / "inventory.json"; write(inv_path, inventory)
    evidence = tmp_path / "synthetic-permission-evidence.txt"; evidence.write_text("Synthetic test only; not a real owner licence or approval.")
    permission = {"source_pdf_sha256": runner.digest(raw), "annotations_sha256": runner.digest(ann_path.read_bytes()),
        "commercial_evaluation_allowed": True, "scope": "LOCAL_COMMERCIAL_DEVELOPMENT_EVALUATION", "evidence_type": "SYNTHETIC",
        "authority_id": "synthetic-test-authority", "evidence_files": [{"path": evidence.name, "sha256": runner.digest(evidence.read_bytes())}]}
    permission["review"] = {"reviewer_id": "synthetic-test-permission-reviewer", "reviewed_at": "2026-11-13T00:00:00+00:00",
        "reviewed_content_sha256": runner.digest(runner.canonical(permission))}
    perm_path = tmp_path / "permissions.json"; write(perm_path, {"schema_version": "medtwin.independent-report-permissions.v1", "records": [permission]})
    return inv_path, ann_path, perm_path


def controlled_prediction(image):
    return {"text": "Glucose 5.8 mg/dL\nCreatinine 1.1 mg/dL\nNo pleural effusion.", "engine": "EXPLICIT_SYNTHETIC_TEST_STUB", "rotation_degrees": 0,
        "fields": [{"name": "glucose", "value": 5.8, "unit": "mg/dL", "specimen": "Urine", "collection_date": "2026-10-01", "report_date": "2026-10-02", "result_operator": "<", "reference_low": 1., "reference_high": 2., "source_bbox": [10, 10, 180, 60]},
            {"name": "creatinine", "value": 1.1, "unit": "mg/dL", "source_bbox": [10, 80, 180, 100]}],
        "entities": [{"entity_text": "pleural effusion", "category": "FINDING", "certainty": "CERTAIN", "negation": "AFFIRMED", "temporality": "CURRENT", "source_bbox": [10, 200, 180, 240]}]}


def evaluate(bundle, **kwargs):
    return runner.evaluate(*bundle, synthetic_software_control=True, predictor=controlled_prediction, **kwargs)


def test_source_bound_software_control_counts_misses_spurious_and_critical_errors(bundle):
    before = [path.read_bytes() for path in bundle]
    result = evaluate(bundle)
    assert result["status"] == "SYNTHETIC_SOFTWARE_CONTROL"
    assert result["counts"]["independent_real_pages"] == result["counts"]["independent_real_documents"] == 0
    assert result["metrics"]["lab"]["precision"] == result["metrics"]["lab"]["recall"] == .5
    assert result["metrics"]["lab"]["value_and_unit_exact_match_rate_at_tolerance"] == 0.
    for error in ("lab_missing", "lab_spurious", "lab_value_mismatch", "lab_unit_mismatch", "lab_comparator_mismatch", "lab_specimen_mismatch", "lab_collection_date_mismatch", "lab_report_date_mismatch", "lab_reference_interval_mismatch", "nlp_source_region_negation_mismatch"):
        assert result["error_breakdown"][error] == 1
    assert result["metrics"]["ocr"]["character_error_rate"] > 0.
    assert result["references"]["full_report_page_coverage_verified"] is True
    assert result["provenance"]["verified_source_bindings"] is True
    assert result["publication_scope"] == "PRIVATE_OPERATOR_EVALUATION"
    assert [path.read_bytes() for path in bundle] == before
    output = json.dumps(result)
    assert "Glucose" not in output and "pleural effusion" not in output and str(bundle[0].parent) not in output
    assert runner.validate_result(result)


def test_software_control_requires_explicit_flag_and_no_real_counts(bundle):
    with pytest.raises(runner.Refused, match="SYNTHETIC_CONTROL"):
        runner.evaluate(*bundle, predictor=controlled_prediction)


@pytest.mark.parametrize("mutation,code", [
    (lambda p: p["records"][0].update(commercial_evaluation_allowed=False), "COMMERCIAL_EVALUATION_SCOPE_NOT_GRANTED"),
    (lambda p: p["records"][0].update(annotations_sha256="0" * 64), "PERMISSION_REFERENCE_HASH_BINDING_REQUIRED"),
    (lambda p: p["records"][0]["review"].update(reviewed_content_sha256="0" * 64), "PERMISSION_REVIEW_CONTENT_HASH_MISMATCH"),
])
def test_permission_gates_precede_any_ocr(bundle, monkeypatch, mutation, code):
    permission = runner.read_json(bundle[2]); mutation(permission); write(bundle[2], permission)
    with pytest.raises(runner.Refused, match=code): evaluate(bundle)


def test_changed_permission_evidence_is_rejected_before_predictions(bundle):
    (bundle[0].parent / "synthetic-permission-evidence.txt").write_text("changed")
    with pytest.raises(runner.Refused, match="EVIDENCE_HASH_MISMATCH"): evaluate(bundle)


@pytest.mark.parametrize("field", ["used_for_training_or_tuning", "predictions_visible_to_annotators"])
def test_exposed_reference_is_not_an_independent_evaluation(bundle, field):
    inventory = runner.read_json(bundle[0]); inventory["reference_provenance"][field] = True; write(bundle[0], inventory)
    with pytest.raises(runner.Refused, match="EXPOSED_OR_UNDECLARED"): evaluate(bundle)


def test_model_application_export_is_not_gold(bundle):
    write(bundle[1], {"findings": [], "measurements": [], "analysis_jobs": []})
    with pytest.raises(runner.Refused, match="ANNOTATION_ADAPTER_REQUIRED"): evaluate(bundle)


def test_partial_target_labels_cannot_support_missed_spurious_metrics(bundle):
    inventory = runner.read_json(bundle[0]); inventory["reference_provenance"]["target_annotations_complete"] = False; write(bundle[0], inventory)
    with pytest.raises(runner.Refused, match="EXHAUSTIVE_TARGET_ANNOTATION"): evaluate(bundle)


def test_changed_reviewed_annotation_rejected_without_auto_finalization(bundle):
    annotations = runner.read_json(bundle[1]); annotations["pages"][0]["fields"][0]["value"] = "52"; write(bundle[1], annotations)
    with pytest.raises(runner.Refused, match="ANNOTATIONS_NOT_FINALIZED"): evaluate(bundle)


@pytest.mark.parametrize("kind", ["page_count", "missing_page", "wrong_dimensions", "image_hash"])
def test_full_report_page_and_raster_binding_rejects_partial_or_wrong_input(bundle, kind):
    inventory = runner.read_json(bundle[0]); document = inventory["documents"][0]
    if kind == "page_count": document["page_count"] = 2
    elif kind == "missing_page": document["pages"] = []
    elif kind == "wrong_dimensions": document["pages"][0]["width"] += 1
    else: document["pages"][0]["source_image_sha256"] = "0" * 64
    write(bundle[0], inventory)
    with pytest.raises(runner.Refused): evaluate(bundle)


def test_correct_pdf_hash_cannot_substitute_for_source_raster_hash(bundle):
    inventory = runner.read_json(bundle[0]); document = inventory["documents"][0]
    document["pages"][0]["source_image_sha256"] = document["source_pdf_sha256"]; write(bundle[0], inventory)
    with pytest.raises(runner.Refused, match="HASH_MISMATCH"): evaluate(bundle)


def test_readable_page_without_transcription_is_precisely_unsupported(bundle):
    annotations = runner.read_json(bundle[1]); annotations["pages"][0]["gold_text"] = None; write(bundle[1], annotations)
    with pytest.raises(runner.Refused, match="FULL_TRANSCRIPTION_REQUIRED_BY_THIS_ANNOTATION_ADAPTER"): evaluate(bundle)


def test_cli_refusal_is_sanitized_and_does_not_overwrite_source_or_output(bundle, tmp_path, monkeypatch, capsys):
    args = ["--inventory", str(bundle[0]), "--annotations", str(bundle[1]), "--permissions", str(bundle[2]), "--out", str(tmp_path / "aggregate.json"), "--synthetic-software-control"]
    monkeypatch.setattr(runner, "predict_page", controlled_prediction)
    assert runner.main(args) == 0
    first = (tmp_path / "aggregate.json").read_bytes()
    assert runner.main(args) == 2
    assert (tmp_path / "aggregate.json").read_bytes() == first
    messages = capsys.readouterr().out
    assert "Glucose" not in messages and str(tmp_path) not in messages
    assert "SYNTHETIC_SOFTWARE_CONTROL" in messages and "REFUSED" in messages


def test_real_output_is_not_written_inside_repository(bundle, capsys):
    args = ["--inventory", str(bundle[0]), "--annotations", str(bundle[1]), "--permissions", str(bundle[2]), "--out", str(ROOT / "must-not-write-independent-report.json")]
    assert runner.main(args) == 2
    assert "PRIVATE_OUTPUT_MUST_BE_OUTSIDE_REPOSITORY_OR_GIT_IGNORED_CACHE_ARTIFACTS" in capsys.readouterr().out
    assert not (ROOT / "must-not-write-independent-report.json").exists()


def test_local_cache_output_requires_actual_git_ignore_and_tracked_source_refuses():
    assert runner._output_allowed(ROOT / ".cache" / "independent-test-control" / "new-aggregate.json") is True
    assert runner._output_allowed(ROOT / "src" / "private-aggregate.json") is False
    assert runner._output_allowed(ROOT / "docs" / "private-aggregate.json") is False
