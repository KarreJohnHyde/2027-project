"""Comparison safeguards operate on actual labelled patient units, not counts."""
from copy import deepcopy
import csv
import json
import pytest
from app.services import universal_arena as arena


@pytest.fixture
def registered(tmp_path, monkeypatch):
    def make(mid, ids=("r1", "r2"), patients=("p1", "p2"), truths=("0", "1"), task="multilabel_ecg_classification"):
        prediction = tmp_path / f"{mid}.csv"
        with prediction.open("w", newline="") as handle:
            writer = csv.writer(handle); writer.writerow(["record_id", "patient_id", "y_A", "p_A"])
            writer.writerows((rid, patient, truth, .5) for rid, patient, truth in zip(ids, patients, truths))
        report = tmp_path / f"{mid}.json"
        report.write_text(json.dumps({"model_id": mid, "dataset_version": "frozen-v1", "checkpoint_sha256": "registered", "held_out_predictions": str(prediction), "test_n": len(ids), "test_patients": len(set(patients)), "metrics": {"score": .8}}))
        return {"model_id": mid, "task": task, "research_inference": True, "supported_classes": ["A"], "artifact_bundle": {"dataset_version": "frozen-v1", "label_definition": {"classes": ["A"], "source": "fixture"}, "evaluation_report_path": str(report), "held_out_predictions_path": str(prediction), "checkpoint_sha256": "registered"}}
    a, b = make("a"), make("b")
    entries = [a, b]
    monkeypatch.setattr(arena.model_inference, "_load_registry", lambda: {"models": entries})
    monkeypatch.setattr(arena.model_inference, "research_gate", lambda m: {"allowed": False, "blockers": ["RESEARCH_ONLY_FIXTURE"]})
    monkeypatch.setattr(arena.model_inference, "evaluation_summary", lambda m: {"score": .8 if m["model_id"] == "a" else .9, "test_n": 2})
    monkeypatch.setattr(arena, "_evaluation_rights", lambda m: {"allowed": True, "reason": "EXPLICIT_SYNTHETIC_TEST_FIXTURE"})
    arena._csv_units.cache_clear()
    return make, entries


def test_same_labelled_patient_records_compare_despite_serving_block(registered):
    result = arena.compare_models("a", "b")
    assert result["status"] == "COMPARABLE_RECORDED_COHORT"
    assert result["right_minus_left"] == {"score": pytest.approx(.1)}
    assert result["cohorts"]["left"]["n"] == 2
    assert result["significance"] == "NOT_COMPUTED_NO_SUPERIORITY_CLAIM"
    assert result["clinical_activation"] is False


@pytest.mark.parametrize("changes", [{"ids": ("r1", "r3")}, {"patients": ("p1", "p3")}, {"truths": ("1", "1")}])
def test_equal_counts_do_not_establish_matched_cohort(registered, changes):
    make, entries = registered
    entries[1] = make("b", **changes)
    result = arena.compare_models("a", "b")
    assert "HELD_OUT_PATIENT_RECORD_OR_LABEL_MISMATCH" in result["reasons"]
    assert result["right_minus_left"] == {}


def test_duplicate_units_and_absent_patient_keys_fail_closed(registered):
    make, entries = registered
    entries[1] = make("b", ids=("r1", "r1"))
    result = arena.compare_models("a", "b")
    assert result["cohorts"]["right"]["reason"] == "INVALID_OR_DUPLICATE_LABELLED_UNITS"
    assert result["status"] == "COMPARISON_UNAVAILABLE"


def test_task_labels_version_and_self_comparison_refuse(registered):
    _, entries = registered
    entries[1]["task"] = "object_detection"
    entries[1]["supported_classes"] = ["B"]
    entries[1]["artifact_bundle"]["dataset_version"] = "other"
    result = arena.compare_models("a", "b")
    assert {"TASK_MISMATCH", "LABEL_DEFINITION_MISMATCH_OR_UNKNOWN", "DATASET_VERSION_MISMATCH_OR_UNKNOWN"} <= set(result["reasons"])
    assert arena.compare_models("a", "a")["status"] == "COMPARISON_UNAVAILABLE"
    with pytest.raises(KeyError): arena.compare_models("../../private", "a")


def test_snapshot_hash_tracks_report_bytes_and_never_alters_registry(registered):
    _, entries = registered
    original = deepcopy(entries)
    snapshot = arena.list_models()
    assert len(snapshot["models"][0]["evaluation_sha256"]) == 64
    assert entries == original


@pytest.mark.parametrize("field,value", [("model_id", "different"), ("checkpoint_sha256", "swapped"), ("test_n", 3)])
def test_swapped_report_or_inconsistent_count_never_compares(registered, field, value):
    from pathlib import Path
    _, entries = registered
    path = Path(entries[1]["artifact_bundle"]["evaluation_report_path"])
    report = json.loads(path.read_text()); report[field] = value; path.write_text(json.dumps(report))
    assert arena.compare_models("a", "b")["status"] == "COMPARISON_UNAVAILABLE"
