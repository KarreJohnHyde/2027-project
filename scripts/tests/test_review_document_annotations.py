"""Synthetic schema checks only; no independent clinical pages are provided."""
import copy
import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_document_annotations import annotation_digest, export_ocr, finalize, initialize, main, validate, write_new


def draft(tmp_path):
    (tmp_path / "synthetic.png").write_bytes(b"synthetic placeholder; not a clinical page")
    inventory = {"schema_version": "medtwin.review-page-inventory.v1", "pages": [{
        "document_id": "synthetic-page", "page": 1, "source_image_path": "synthetic.png",
        "width": 100, "height": 100, "deidentified": True,
        "permission_scope": "Synthetic unit-test fixture only", "evidence_type": "SYNTHETIC"}]}
    return initialize(inventory, tmp_path)


def annotated(tmp_path):
    bundle = draft(tmp_path)
    bundle["pages"][0].update(readability="READABLE", gold_text="Glucose 5.2 mmol/L")
    bundle["pages"][0]["fields"] = [{"analyte": "Glucose", "value": "5.2", "value_state": "READABLE",
        "unit": "mmol/L", "specimen": None, "collection_date": None, "report_date": None,
        "reference_interval": {"low": "3.5", "high": "6", "text": "3.5–6"}, "comparator": None,
        "assertion": "CERTAIN", "negation": "AFFIRMED", "temporality": "CURRENT",
        "source_bbox": [1, 1, 99, 10]}]
    return bundle


def reviewed(tmp_path):
    return finalize(annotated(tmp_path), "annotator-a", "reviewer-b", manual=True, checked=True)


def test_initializer_does_not_fill_labels_and_reports_zero_completed_pages(tmp_path):
    bundle = draft(tmp_path)
    assert bundle["pages"][0]["gold_text"] is None
    assert bundle["pages"][0]["fields"] == []
    assert validate(bundle)["finalized_real_pages"] == 0
    assert validate(bundle)["finalized_synthetic_pages"] == 0
    assert "source_image_path" not in bundle["pages"][0]
    with pytest.raises(ValueError, match="finalized"):
        export_ocr(bundle)


def test_empty_inventory_is_not_a_successful_gold_evaluation(tmp_path):
    bundle = initialize({"schema_version": "medtwin.review-page-inventory.v1", "pages": []}, tmp_path)
    assert validate(bundle)["total_pages"] == 0
    with pytest.raises(ValueError, match="empty gold"):
        export_ocr(bundle)


@pytest.mark.parametrize("annotator,reviewer,manual,checked", [("a", "A", True, True), ("a", "b", False, True), ("a", "b", True, False), (None, "b", True, True)])
def test_finalization_requires_distinct_identities_and_both_attestations(tmp_path, annotator, reviewer, manual, checked):
    with pytest.raises(ValueError):
        finalize(annotated(tmp_path), annotator, reviewer, manual=manual, checked=checked)


def test_review_is_content_bound_and_synthetic_never_counts_as_real(tmp_path):
    bundle = reviewed(tmp_path)
    counts = validate(bundle)
    assert counts["finalized_real_pages"] == 0
    assert counts["finalized_synthetic_pages"] == 1
    assert counts["annotated_fields"] == 1
    bundle["pages"][0]["fields"][0]["value"] = "52"
    with pytest.raises(ValueError, match="content changed"):
        export_ocr(bundle)


def test_export_exactly_matches_existing_ocr_evaluator_schema(tmp_path):
    result = export_ocr(reviewed(tmp_path))
    assert set(result) == {"schema_version", "artifact_role", "pages"}
    assert result["schema_version"] == "medtwin.ocr-pages.v1"
    assert result["artifact_role"] == "gold"
    assert set(result["pages"][0]) == {"document_id", "page", "source_image_sha256", "text"}
    assert result["pages"][0]["text"] == "Glucose 5.2 mmol/L"


@pytest.mark.parametrize("mutation", [
    lambda page: page.update(deidentified=False),
    lambda page: page.update(permission_scope=""),
    lambda page: page.update(source_image_sha256="wrong"),
    lambda page: page.update(evidence_type="MODEL_GENERATED_GOLD"),
    lambda page: page["fields"][0].update(source_bbox=[0, 0, 101, 100]),
    lambda page: page["fields"][0].update(source_bbox=[0, 0, float("nan"), 1]),
    lambda page: page["fields"][0].update(value="NaN"),
    lambda page: page["fields"][0].update(value="<5"),
    lambda page: page["fields"][0].update(value_state="UNREADABLE"),
    lambda page: page["fields"][0].update(collection_date="11/13/2026"),
    lambda page: page["fields"][0].update(assertion="CONFIRMED_DIAGNOSIS"),
    lambda page: page["fields"][0].update(reference_interval={"low": "6", "high": "3", "text": "wrong"}),
])
def test_invalid_sources_values_units_dates_and_coordinates_fail_closed(tmp_path, mutation):
    bundle = annotated(tmp_path)
    mutation(bundle["pages"][0])
    with pytest.raises(ValueError):
        validate(bundle)


def test_unreadable_values_are_null_and_unreadable_pages_are_excluded(tmp_path):
    bundle = annotated(tmp_path)
    field = bundle["pages"][0]["fields"][0]
    field.update(value_state="UNREADABLE", value=None, unreadable_reason="Synthetic unreadable number")
    assert validate(bundle)["annotated_fields"] == 1
    bundle["pages"][0].update(readability="UNREADABLE", gold_text=None, fields=[], unreadable_reason="Synthetic unreadable page")
    finalize(bundle, "a", "b", manual=True, checked=True)
    assert validate(bundle)["unreadable_finalized_pages"] == 1
    with pytest.raises(ValueError, match="empty gold"):
        export_ocr(bundle)


def test_unannotated_pages_cannot_be_finalized(tmp_path):
    with pytest.raises(ValueError, match="Complete annotation"):
        finalize(draft(tmp_path), "a", "b", manual=True, checked=True)


def test_entity_spans_require_source_coordinates_and_strict_context(tmp_path):
    bundle = annotated(tmp_path)
    bundle["pages"][0]["entities"] = [{"start": 0, "end": 7, "label": "ANALYTE", "assertion": "CERTAIN",
        "negation": "AFFIRMED", "temporality": "CURRENT", "source_bbox": [1, 1, 30, 10]}]
    assert validate(bundle)["annotated_entities"] == 1
    bundle["pages"][0]["entities"][0]["end"] = 1000
    with pytest.raises(ValueError, match="offsets"):
        validate(bundle)


def test_duplicate_pages_and_overwrite_are_refused(tmp_path):
    bundle = draft(tmp_path)
    bundle["pages"].append(copy.deepcopy(bundle["pages"][0]))
    with pytest.raises(ValueError, match="Duplicate"):
        validate(bundle)
    target = tmp_path / "retained.json"
    write_new(target, {"original": True})
    with pytest.raises(FileExistsError):
        write_new(target, {"original": False})
    assert json.loads(target.read_text()) == {"original": True}


def test_cli_validates_without_creating_reference_answers(tmp_path, capsys):
    target = tmp_path / "draft.json"
    write_new(target, draft(tmp_path))
    assert main(["--validate", str(target)]) == 0
    assert json.loads(capsys.readouterr().out)["finalized_real_pages"] == 0
