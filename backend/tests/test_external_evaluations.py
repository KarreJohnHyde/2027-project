"""Saved external evaluations reach the registry only for the checkpoint they measured, and never as clinical validation.
Synthetic evaluation files only, except the last test, which reads the committed CQ500 result."""

import json

import pytest

from app.services import external_evaluations
from app.services.model_registry import get_model

SHA = "ab" * 32


def evaluation(model_id="demo_model", sha=SHA, clinical_validation=False):
    return {
        "dataset": "Synthetic cohort", "reference": "majority read",
        "cohort": {"scope": "FULL_REFERENCED_COHORT_EXCEPT_DOCUMENTED_SOURCE_DEFECTS", "expected_reference_scans": 3,
                   "excluded_source_defects": {"SCAN-2": {"reason": "truncated at the source", "series": []}},
                   "clinical_validation": clinical_validation},
        "models": {model_id: {"scans": 2, "scored": 1, "refused": 1, "per_label": {"ANY": {
            "positives": 1, "negatives": 0, "auroc": 0.9,
            "auroc_ci95": {"status": "COMPUTED", "low": 0.8, "high": 0.95},
            "sensitivity_at_rsna_threshold": 1.0, "specificity_at_rsna_threshold": 0.5}}}},
        "checkpoint_sha256": {model_id: sha},
        "threshold_policy": "frozen", "metric_population": "scored scans only",
    }


@pytest.fixture
def folder(tmp_path, monkeypatch):
    monkeypatch.setattr(external_evaluations, "EVALUATION_DIR", tmp_path)
    return tmp_path


def model(sha=SHA):
    return {"model_id": "demo_model", "artifact_bundle": {"checkpoint_sha256": sha}}


def test_a_result_for_the_registered_checkpoint_is_summarised(folder):
    (folder / "demo.json").write_text(json.dumps(evaluation()), encoding="utf-8")
    (found,) = external_evaluations.external_evaluations_for(model())
    assert found["clinical_validation"] is False
    assert (found["scored"], found["refused"]) == (1, 1)
    assert found["excluded"] == [{"scan": "SCAN-2", "reason": "truncated at the source"}]
    assert found["labels"] == [{"label": "ANY", "positives": 1, "negatives": 0, "auroc": 0.9, "auroc_ci95": [0.8, 0.95],
                                "sensitivity": 1.0, "specificity": 0.5}]


def test_a_result_for_another_checkpoint_is_not_attached(folder):
    (folder / "demo.json").write_text(json.dumps(evaluation(sha="cd" * 32)), encoding="utf-8")
    assert external_evaluations.external_evaluations_for(model()) == []


def test_a_file_that_does_not_disclaim_clinical_validation_is_ignored(folder):
    (folder / "demo.json").write_text(json.dumps(evaluation(clinical_validation=True)), encoding="utf-8")
    (folder / "other.json").write_text(json.dumps({"model_id": "demo_model", "metrics": {}}), encoding="utf-8")
    (folder / "broken.json").write_text("{not json", encoding="utf-8")
    assert external_evaluations.external_evaluations_for(model()) == []


def test_a_model_without_a_registered_checkpoint_gets_nothing(folder):
    (folder / "demo.json").write_text(json.dumps(evaluation()), encoding="utf-8")
    assert external_evaluations.external_evaluations_for(model(sha="")) == []


def test_the_committed_cq500_result_reaches_the_haemorrhage_classifier():
    registered = get_model("brain_ct_rsna_ich_classifier")
    if registered is None:
        pytest.skip("haemorrhage classifier not registered in this checkout")
    (found,) = [item for item in registered.get("external_evaluation", []) if item["report_path"].endswith("head_ct_cq500_external.json")]
    assert found["scope"] == "FULL_REFERENCED_COHORT_EXCEPT_DOCUMENTED_SOURCE_DEFECTS"
    assert [item["scan"] for item in found["excluded"]] == ["CQ500-CT-120"]
    assert found["clinical_validation"] is False
    assert found["checkpoint_sha256"] == registered["artifact_bundle"]["checkpoint_sha256"]
