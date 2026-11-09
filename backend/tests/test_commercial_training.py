"""Commercial purpose cannot inherit research-only data permissions."""
import hashlib
import json
import pytest
from ml_training import volumetric_manifest as vm


def gate(tmp_path, monkeypatch, name, review=None):
    context = tmp_path / "context.json"
    context.write_text(json.dumps({"training_purpose": "commercial_development"}))
    monkeypatch.setattr(vm, "RELEASE_CONTEXT", context)
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "research")
    registry = tmp_path / "registry.json"
    registry.write_text(json.dumps({"datasets": [{"id": "fixture", "license": {
        "name": name, "authorization_status": "VERIFIED", "commercial_development_review": review,
    }}]}))
    return lambda: vm.enforce_training_license({"dataset_id": "fixture"}, registry)


@pytest.mark.parametrize("terms", ["CC BY-NC-SA 4.0", "research only", "research and educational purposes only"])
def test_noncommercial_terms_are_blocked_even_in_research_runtime(tmp_path, monkeypatch, terms):
    with pytest.raises(vm.LicenseAuthorizationError, match="non-commercial/research-only"):
        gate(tmp_path, monkeypatch, terms)()


def test_permissive_or_unknown_terms_still_need_reviewed_commercial_scope(tmp_path, monkeypatch):
    for terms in ["CC BY 4.0", "Terms not found"]:
        with pytest.raises(vm.LicenseAuthorizationError, match="separate, evidence-bound review"):
            gate(tmp_path, monkeypatch, terms)()


def test_commercial_review_is_bound_to_actual_evidence(tmp_path, monkeypatch):
    source = tmp_path / "synthetic-rights.txt"
    source.write_text("Synthetic review fixture only, not an actual rights grant.")
    review = {"status": "REVIEWED_FOR_DECLARED_COMMERCIAL_DEVELOPMENT", "reviewer": "Test fixture",
              "reviewed_at": "2026-11-09", "declared_use": "Synthetic gate test only",
              "evidence_files": [{"path": str(source), "sha256": hashlib.sha256(source.read_bytes()).hexdigest()}]}
    run = gate(tmp_path, monkeypatch, "CC BY 4.0", review)
    assert run()["training_purpose"] == "commercial_development"
    source.write_text("Changed fixture")
    with pytest.raises(vm.LicenseAuthorizationError, match="evidence"):
        run()


def test_missing_release_context_fails_closed(tmp_path, monkeypatch):
    run = gate(tmp_path, monkeypatch, "CC BY 4.0")
    vm.RELEASE_CONTEXT.unlink()
    with pytest.raises(vm.LicenseAuthorizationError, match="declared training purpose"):
        run()
