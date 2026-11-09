"""A complete training job is not evidence that every declared target was learned."""
import hashlib

import pytest

from app.services import model_inference
from scripts.publish_brain_mri_models import research_quality_assessment


def test_zero_dice_with_positive_references_rejects_the_declared_target():
    result = research_quality_assessment({"per_structure": {
        "kidney": {"reference_positive_cases": 32, "mean_dice": 0.83},
        "renal_tumour": {"reference_positive_cases": 32, "mean_dice": 0.0},
    }})
    assert result["status"] == "FAILED_DECLARED_TARGET"
    assert result["failed_targets"] == ["renal_tumour"]
    assert research_quality_assessment({"per_structure": {"lesion": {
        "reference_positive_cases": 0, "mean_dice": None}}})["status"] == "METRICS_RECORDED_NOT_CLINICALLY_VALIDATED"


def test_target_failure_blocks_upload_even_with_intact_artifacts_and_ready_status(tmp_path, monkeypatch):
    checkpoint = tmp_path / "synthetic.pt"
    checkpoint.write_bytes(b"not a clinical model")
    report = tmp_path / "report.json"
    report.write_text("{}")
    model = {"model_id": "rejected", "display_name": "Synthetic rejected model", "research_inference": True,
             "status": "READY_UNVALIDATED", "inference_input": "volume_nifti",
             "research_quality_assessment": {"status": "FAILED_DECLARED_TARGET", "failed_targets": ["tumour"]},
             "artifact_bundle": {"checkpoint_path": str(checkpoint), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                                 "dataset_license": "Synthetic test only", "evaluation_report_path": str(report)}}
    monkeypatch.setenv("MEDTWIN_USAGE_PROFILE", "research")
    assert model_inference.research_gate(model) == {"allowed": False, "blockers": ["DECLARED_TARGET_FAILED_EVALUATION"]}
    monkeypatch.setattr(model_inference, "_load_registry", lambda: {"models": [model]})
    with pytest.raises(model_inference.InferenceNotPermitted, match="DECLARED_TARGET_FAILED_EVALUATION"):
        model_inference.get_model("rejected")
