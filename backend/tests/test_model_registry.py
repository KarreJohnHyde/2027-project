"""Model/capability registry contract and activation-gate tests."""

from copy import deepcopy
import hashlib

from app.services.model_registry import activation_gate, list_models
from tests.conftest import get_auth_headers


def test_model_registry_requires_authentication(client):
    assert client.get("/api/v1/models").status_code == 401
    assert client.get("/api/v1/capabilities").status_code == 401


def test_registry_exposes_truthful_non_activatable_statuses(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    response = client.get("/api/v1/models", headers=headers)

    assert response.status_code == 200
    payload = response.json()
    assert payload["schema_version"] == "1.0.0"
    assert payload["model_count"] >= 10
    assert payload["activatable_count"] == 0

    models = {item["model_id"]: item for item in payload["models"]}
    assert models["clinical_rules_v1"]["status"] == "READY_UNVALIDATED"
    assert models["clinical_rules_v1"]["processor_only"] is True
    assert models["mura_study_baseline"]["status"] == "WEIGHTS_MISSING"
    # Trained on PTB-XL 1.0.1 (ml_training/ecg.py): research evidence, never clinically activatable.
    assert models["ptbxl_ecg_baseline"]["status"] == "READY_UNVALIDATED"
    assert models["ptbxl_ecg_baseline"]["validated"] is False
    assert models["ptbxl_ecg_baseline"]["inference_input"] == "ecg_12lead"
    assert models["medcat_adapter"]["status"] == "DEPENDENCY_MISSING"
    assert all(not item["activation"]["eligible"] for item in models.values())


def test_model_detail_and_activation_explain_missing_bundle(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])

    detail = client.get("/api/v1/models/mura_study_baseline", headers=headers)
    assert detail.status_code == 200
    assert "checkpoint_path" in detail.json()["activation"]["missing_fields"]

    activation = client.get(
        "/api/v1/models/mura_study_baseline/activation", headers=headers
    )
    assert activation.status_code == 200
    assert activation.json()["activation"]["eligible"] is False
    assert "ARTIFACT_BUNDLE_INCOMPLETE" in activation.json()["activation"]["blockers"]

    assert client.get("/api/v1/models/not-registered", headers=headers).status_code == 404


def test_capability_registry_separates_processing_from_inference(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    response = client.get("/api/v1/capabilities", headers=headers)

    assert response.status_code == 200
    capabilities = {
        item["capability_id"]: item for item in response.json()["capabilities"]
    }
    assert capabilities["document_parsing"]["operational"] is True
    assert capabilities["clinical_text_rules"]["verification_status"] == "IMPLEMENTED_NOT_VALIDATED"
    assert capabilities["image_preprocessing"]["inference_operational"] is False
    assert capabilities["ecg_quality_preview"]["inference_operational"] is False
    assert capabilities["multimodal_fusion"]["operational"] is False


def test_complete_bundle_requires_matching_checkpoint_hash(tmp_path):
    artifact_paths = {}
    for name in ("split.json", "checkpoint.pt", "predictions.json", "evaluation.json", "model-card.md"):
        path = tmp_path / name
        path.write_text(name, encoding="utf-8")
        artifact_paths[name] = str(path)

    base = deepcopy(list_models()["models"][0])
    base.update({"status": "VALIDATED", "validated": True, "processor_only": False})
    base["artifact_bundle"] = {
        "dataset_version": "test-v1",
        "dataset_license": "TEST-ONLY",
        "split_manifest_path": artifact_paths["split.json"],
        "task_definition": "Synthetic gate unit test only.",
        "label_definition": {"negative": 0, "positive": 1},
        "preprocessing_version": "test-v1",
        "checkpoint_path": artifact_paths["checkpoint.pt"],
        "checkpoint_sha256": hashlib.sha256(b"checkpoint.pt").hexdigest(),
        "calibration": {"method": "temperature", "parameters": {"temperature": 1.0}},
        "decision_thresholds": {"positive": 0.5},
        "abstention_thresholds": {"minimum_confidence": 0.7},
        "held_out_predictions_path": artifact_paths["predictions.json"],
        "evaluation_report_path": artifact_paths["evaluation.json"],
        "model_card_path": artifact_paths["model-card.md"],
    }

    passed = activation_gate(base)
    assert passed["eligible"] is True
    assert passed["checkpoint_hash_matches"] is True

    base["artifact_bundle"]["checkpoint_sha256"] = "0" * 64
    failed = activation_gate(base)
    assert failed["eligible"] is False
    assert "CHECKPOINT_HASH_MISMATCH" in failed["blockers"]
