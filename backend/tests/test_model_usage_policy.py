import hashlib
import json
import pytest

from app.services import model_usage_policy as policy


def test_production_defaults_to_commercial_even_without_profile(monkeypatch):
    monkeypatch.delenv("MEDTWIN_USAGE_PROFILE", raising=False)
    monkeypatch.setattr(policy, "ENVIRONMENT", "production")
    result = policy.usage_gate({"model_id": "unreviewed-test"})
    assert result["profile"] == "commercial"
    assert not result["allowed"]


def test_commercial_profile_refuses_missing_or_unreviewed_rights(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "commercial")
    path = tmp_path / "review.json"
    monkeypatch.setenv("MEDTWIN_COMMERCIAL_REVIEW_PATH", str(path))
    model = {"model_id": "test", "artifact_bundle": {"checkpoint_sha256": "a" * 64}}
    assert not policy.usage_gate(model)["allowed"]
    path.write_text(json.dumps({"schema_version": 1, "models": [{"model_id": "test", "checkpoint_sha256": "a" * 64}]}))
    result = policy.usage_gate(model)
    assert not result["allowed"]
    assert "COMMERCIAL_SOURCE_DATA_RIGHTS_NOT_REVIEWED" in result["blockers"]


def test_review_is_bound_to_model_version_and_immutable_evidence(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "commercial")
    evidence = tmp_path / "synthetic-permission.txt"
    evidence.write_text("Synthetic permission test fixture; no real rights grant.")
    path = tmp_path / "review.json"
    monkeypatch.setenv("MEDTWIN_COMMERCIAL_REVIEW_PATH", str(path))
    row = {"model_id": "test", "checkpoint_sha256": "a" * 64, "reviewer": "Synthetic test reviewer",
           "reviewed_at": "2026-11-09", "declared_use": "Test fixture only",
           **{field: "REVIEWED_FOR_DECLARED_COMMERCIAL_USE" for field in ("source_data_rights", "code_rights", "weights_rights", "redistribution_rights")},
           "evidence_files": [{"path": str(evidence), "sha256": hashlib.sha256(evidence.read_bytes()).hexdigest()}]}
    path.write_text(json.dumps({"schema_version": 1, "models": [row]}))
    assert policy.usage_gate({"model_id": "test", "artifact_bundle": {"checkpoint_sha256": "a" * 64}})["allowed"]
    assert not policy.usage_gate({"model_id": "test", "artifact_bundle": {"checkpoint_sha256": "b" * 64}})["allowed"]
    evidence.write_text("Altered evidence")
    assert not policy.usage_gate({"model_id": "test", "artifact_bundle": {"checkpoint_sha256": "a" * 64}})["allowed"]


def test_research_and_invalid_profiles_are_distinct(monkeypatch):
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "research")
    assert policy.usage_gate({"model_id": "test"})["allowed"]
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "typo")
    assert not policy.usage_gate({"model_id": "test"})["allowed"]


def test_malformed_commercial_records_fail_closed(tmp_path, monkeypatch):
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "commercial")
    path = tmp_path / "malformed.json"
    path.write_text(json.dumps({"schema_version": 1, "models": ["not a model record"]}))
    monkeypatch.setenv("MEDTWIN_COMMERCIAL_REVIEW_PATH", str(path))
    assert policy.usage_gate({"model_id": "test"})["blockers"] == ["COMMERCIAL_REVIEW_UNAVAILABLE"]


@pytest.mark.parametrize("adapter", ["radgraph", "clinical", "scispacy"])
def test_commercial_secondary_models_refuse_before_starting_a_worker(adapter, monkeypatch):
    from app.services import radgraph_adapter, clinical_nlp_adapter, scispacy_adapter
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "commercial")
    def forbidden(*args, **kwargs):
        pytest.fail("An unreviewed commercial model must not start a model or text worker")
    if adapter == "radgraph":
        monkeypatch.setattr(radgraph_adapter, "_model", forbidden)
        with pytest.raises(radgraph_adapter.RadGraphUnavailable, match="COMMERCIAL_"):
            radgraph_adapter.run_model(["synthetic test sentence"])
    elif adapter == "clinical":
        with pytest.raises(clinical_nlp_adapter.ClinicalNlpUnavailable, match="COMMERCIAL_"):
            clinical_nlp_adapter.analyse("synthetic test sentence", [], runner=forbidden)
    else:
        with pytest.raises(scispacy_adapter.ScispacyUnavailable, match="COMMERCIAL_"):
            scispacy_adapter.model_statements("synthetic test sentence", runner=forbidden)


def test_legacy_radgraph_is_not_imported_or_started_in_production(monkeypatch):
    from app.services import radgraph_adapter
    monkeypatch.setattr(radgraph_adapter, "ENVIRONMENT", "production")
    monkeypatch.setenv("MEDTWIN_RADGRAPH", "on")
    def forbidden():
        pytest.fail("Production must not even probe/import the legacy optional stack")
    monkeypatch.setattr(radgraph_adapter, "installed", forbidden)
    monkeypatch.setattr(radgraph_adapter, "_model", forbidden)
    assert radgraph_adapter.enabled()
    with pytest.raises(radgraph_adapter.RadGraphUnavailable, match="NOT_APPROVED_FOR_PRODUCTION"):
        radgraph_adapter.run_model(["synthetic sentence"])
