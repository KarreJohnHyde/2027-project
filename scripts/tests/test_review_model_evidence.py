import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from review_model_evidence import audit, inspect_model, local_path, sha256, write_outputs


def fixture_model(tmp_path):
    (tmp_path / "checkpoint.pt").write_bytes(b"synthetic checksum test; not model weights")
    digest = sha256(tmp_path / "checkpoint.pt")
    report = {"model_id": "synthetic", "dataset_version": "v1", "checkpoint": {"sha256": digest}, "test": {"n_images": 3, "metrics": {"ap_50": .2}}, "run_id": "synthetic-test"}
    (tmp_path / "report.json").write_text(json.dumps(report))
    model = {"model_id": "synthetic", "task": "object_detection", "research_inference": True, "status": "READY_UNVALIDATED", "artifact_bundle": {"checkpoint_path": "checkpoint.pt", "checkpoint_sha256": digest, "evaluation_report_path": "report.json", "dataset_version": "v1"}}
    return model, report


def test_matching_checkpoint_and_report_remain_historical_and_unverified_runtime(tmp_path):
    model, _ = fixture_model(tmp_path)
    row = inspect_model(tmp_path, model, None)
    assert row["checkpoint_integrity"] == "MATCH"
    assert row["binding_issues"] == ""
    assert row["sample_count"] == 3
    assert row["measurement_origin"] == "HISTORICAL_RECORDED_NOT_REPRODUCED"
    assert row["runtime"] == "UNVERIFIED_BY_READ_ONLY_AUDIT"
    assert "MISSING_FROM_SAVED_SNAPSHOT" in row["snapshot_issues"]


def test_checkpoint_and_report_identity_mismatches_are_not_silently_accepted(tmp_path):
    model, report = fixture_model(tmp_path)
    (tmp_path / "checkpoint.pt").write_bytes(b"changed")
    report.update(model_id="wrong", dataset_version="wrong", checkpoint={"sha256": "wrong"})
    (tmp_path / "report.json").write_text(json.dumps(report))
    row = inspect_model(tmp_path, model, {})
    assert row["checkpoint_integrity"] == "HASH_MISMATCH"
    for problem in ("MODEL_ID", "DATASET_VERSION", "CHECKPOINT_HASH"):
        assert problem in row["binding_issues"]


def test_failed_target_is_retained_and_no_activation_is_performed(tmp_path):
    model, _ = fixture_model(tmp_path)
    model["status"] = "FAILED"
    row = inspect_model(tmp_path, model, {"status": "FAILED"})
    assert row["eligibility"].startswith("BLOCKED_FAILED_TARGET")
    assert row["validated_flag"] is False


def test_missing_artifacts_and_outside_paths_are_reported(tmp_path):
    model, _ = fixture_model(tmp_path)
    model["artifact_bundle"]["checkpoint_path"] = "missing.pt"
    model["artifact_bundle"]["evaluation_report_path"] = "missing.json"
    row = inspect_model(tmp_path, model, None)
    assert row["checkpoint_integrity"] == "MISSING"
    assert "EVALUATION_REPORT_MISSING_OR_INVALID" in row["binding_issues"]
    with pytest.raises(ValueError, match="leaves"):
        local_path(tmp_path, "../private.pt")


def test_directory_adapter_is_not_misreported_as_missing_file(tmp_path):
    (tmp_path / "adapter").mkdir()
    row = inspect_model(tmp_path, {"model_id": "adapter", "weights_path": "adapter"}, None)
    assert row["checkpoint_integrity"] == "DIRECTORY_ADAPTER_UNPINNED"


def test_declared_component_checkpoints_are_each_hashed(tmp_path):
    model, _ = fixture_model(tmp_path)
    paths = {}
    for name, trainer in (("component-a", "trainer"), ("component-b", "fast-trainer")):
        target = tmp_path / "weights" / name / trainer / "fold_0/checkpoint.pt"
        target.parent.mkdir(parents=True)
        target.write_bytes(name.encode())
        paths[name] = target
    bundle = model["artifact_bundle"]
    bundle["checkpoint_path"] = "weights/component-a/trainer/fold_0/checkpoint.pt"
    bundle["checkpoint_sha256"] = sha256(tmp_path / bundle["checkpoint_path"])
    bundle["component_checkpoints_sha256"] = {name: sha256(path) for name, path in paths.items()}
    row = inspect_model(tmp_path, model, None)
    components = json.loads(row["component_checkpoint_integrity_json"])
    assert len(components) == 2
    assert all(item["integrity"] == "MATCH" for item in components)


def test_audit_exports_current_registry_not_stale_snapshot_without_mutation(tmp_path):
    model, _ = fixture_model(tmp_path)
    (tmp_path / "model_registry").mkdir()
    registry = tmp_path / "model_registry/models.json"
    registry.write_text(json.dumps({"models": [model]}))
    saved = tmp_path / "model_registry/validation_status.json"
    saved.write_text(json.dumps({"models": [{"model_id": "old"}]}))
    original = registry.read_bytes(), saved.read_bytes()
    payload = audit(tmp_path)
    write_outputs(payload, tmp_path / "out")
    assert payload["summary"]["models"] == 1
    assert payload["summary"]["new_predictive_evaluations"] == 0
    assert payload["snapshot_only_model_ids"] == ["old"]
    assert (tmp_path / "out/MEDTWIN_MODEL_RESULTS_2026-11-13.csv").exists()
    assert original == (registry.read_bytes(), saved.read_bytes())


def test_duplicate_registry_identifiers_are_rejected(tmp_path):
    (tmp_path / "model_registry").mkdir()
    (tmp_path / "model_registry/models.json").write_text(json.dumps({"models": [{"model_id": "a"}, {"model_id": "a"}]}))
    with pytest.raises(ValueError, match="Duplicate"):
        audit(tmp_path)
