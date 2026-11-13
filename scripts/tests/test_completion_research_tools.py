"""No-test-label development and portable/hash-bound operator evidence controls."""
import csv
import json
from pathlib import Path
import sys
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT)); sys.path.insert(0, str(ROOT / "backend"))
from scripts import completion_research_audit as audit
from scripts import completion_ptb_development as development


def metadata(tmp_path, same_patient=False, bad_fold=False):
    statements = tmp_path / "scp.csv"
    statements.write_text(",diagnostic,diagnostic_class\nNORM,1.0,NORM\n", encoding="utf-8")
    path = tmp_path / "metadata.csv"
    with path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=["ecg_id", "patient_id", "strat_fold", "scp_codes", "age", "sex"])
        writer.writeheader()
        writer.writerow({"ecg_id": "1", "patient_id": "train", "strat_fold": 0 if bad_fold else 1, "scp_codes": "{'NORM': 100}", "age": 40, "sex": 0})
        writer.writerow({"ecg_id": "2", "patient_id": "train" if same_patient else "validation", "strat_fold": 9, "scp_codes": "{'NORM': 100}", "age": 50, "sex": 1})
        # Invalid literal/features prove this row is skipped before parsing.
        writer.writerow({"ecg_id": "3", "patient_id": "test", "strat_fold": 10, "scp_codes": "THIS MUST NEVER BE PARSED", "age": "DO NOT PARSE", "sex": "UNKNOWN"})
    return path, statements


def test_test_fold_excluded_before_labels_and_features_are_parsed(tmp_path):
    path, statements = metadata(tmp_path)
    result = development.read_development(path, statements)
    assert len(result["train"]) == len(result["validation"]) == 1
    assert result["skipped_test_rows_without_label_parsing"] == 1
    assert result["patient_disjoint"] is True


@pytest.mark.parametrize("kwargs", [{"same_patient": True}, {"bad_fold": True}])
def test_development_rejects_patient_leakage_or_unknown_publisher_fold(tmp_path, kwargs):
    path, statements = metadata(tmp_path, **kwargs)
    with pytest.raises(ValueError):
        development.read_development(path, statements)


def test_rights_refusal_precedes_metadata_access(monkeypatch, tmp_path):
    import ml_training.volumetric_manifest as manifest
    def reject(*args, **kwargs):
        raise PermissionError("Commercial evidence review absent")
    monkeypatch.setattr(manifest, "enforce_training_license", reject)
    monkeypatch.setattr(development, "read_development", lambda *args: pytest.fail("Blocked data were accessed"))
    monkeypatch.setattr(sys, "argv", ["development", "--rights-registry", str(tmp_path / "missing.json")])
    with pytest.raises(PermissionError, match="Commercial"):
        development.main()


def test_evidence_records_are_portable_project_relative_and_hash_bound(tmp_path, monkeypatch):
    monkeypatch.setattr(audit, "ROOT", tmp_path)
    source = tmp_path / "nested" / "file.txt"
    source.parent.mkdir(); source.write_text("frozen evidence")
    record = audit.record(source)
    assert record["path"] == "nested/file.txt"
    original = record["sha256"]
    source.write_text("changed evidence")
    assert audit.record(source)["sha256"] != original


def test_known_overlap_is_reported_without_split_mutation(tmp_path):
    path = tmp_path / "samples.csv"
    path.write_text("group_id,split\nsame,train\nsame,val\nother,test\n")
    original = path.read_bytes()
    result = audit.overlap(path)
    assert result["cross_split_group_count"] == 1
    assert path.read_bytes() == original


def test_canonical_commercial_gate_rejects_changed_bound_evidence(tmp_path, monkeypatch):
    import ml_training.volumetric_manifest as manifest
    context = tmp_path / "purpose.json"
    context.write_text(json.dumps({"training_purpose": "commercial_development"}))
    monkeypatch.setattr(manifest, "RELEASE_CONTEXT", context)
    evidence = tmp_path / "exact-primary-license.txt"
    evidence.write_text("Synthetic permissive license evidence for gate unit test")
    sidecar = tmp_path / "sidecar.json"
    sidecar.write_text(json.dumps({"datasets": [{"id": "unit-test-only", "license": {"authorization_status": "VERIFIED", "name": "CC BY 4.0", "commercial_development_review": {
        "status": "REVIEWED_FOR_DECLARED_COMMERCIAL_DEVELOPMENT", "reviewer": "Synthetic test operator", "reviewed_at": "2026-11-13", "declared_use": "Isolated unit test only",
        "evidence_files": [{"path": evidence.as_posix(), "sha256": audit.digest(evidence)}]}}}]}))
    assert manifest.enforce_training_license({"dataset_id": "unit-test-only"}, sidecar)["authorized"] is True
    evidence.write_text("Changed evidence")
    with pytest.raises(PermissionError, match="missing, invalid or changed"):
        manifest.enforce_training_license({"dataset_id": "unit-test-only"}, sidecar)
