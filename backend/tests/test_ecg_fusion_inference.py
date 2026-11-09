"""ECG + age/sex fusion inference: the encoding shared with training, where age and sex come from, and refusals.

The checkpoint is a randomly initialised fusion network saved inside the test and the ECG is synthetic noise;
nothing here is patient evidence or a model result."""

import hashlib
import json

import pytest

torch = pytest.importorskip("torch")

from app.services import ecg_inference, model_inference, model_registry  # noqa: E402
from app.services.ecg_inference import PTBXL_LEADS  # noqa: E402
from tests.conftest import get_auth_headers  # noqa: E402
from tests.test_signal_and_volume_inference import _signal, _wfdb  # noqa: E402


def test_the_served_encoding_matches_the_training_definition():
    assert ecg_inference.demographic_vector(45, "F") == [0.45, 0.0, 1.0, 0.0]
    assert ecg_inference.demographic_vector(300, "M") == [0.9, 0.0, 0.0, 0.0], "PTB-XL codes 90 and over as 300"
    assert ecg_inference.demographic_vector(None, None) == [0.0, 1.0, 0.5, 1.0]


@pytest.fixture
def fusion_registry(tmp_path, monkeypatch):
    torch.manual_seed(0)
    network = ecg_inference.build_network(5, 12, demographic_fusion=True)
    checkpoint = tmp_path / "fusion.pt"
    torch.save({"kind": "ecg_classifier", "arch": ecg_inference.FUSION_ARCH, "state_dict": network.state_dict(), "classes": ["NORM", "MI", "STTC", "CD", "HYP"],
                "leads": PTBXL_LEADS, "sampling_rate_hz": 100, "samples": 1000, "lead_mean_mv": [0.0] * 12, "lead_std_mv": [0.2] * 12,
                "platt": [[1.0, 0.0]] * 5, "thresholds": [0.5] * 5}, checkpoint)
    report = tmp_path / "report.json"
    report.write_text(json.dumps({"test_n": 20, "metrics": {"macro_auroc": 0.8, "macro_auprc": 0.6, "macro_f1_at_validation_thresholds": 0.5},
                                  "arms": {"ecg_only": {"macro_auroc": 0.79}},
                                  "paired_difference": {"macro_auroc": 0.01, "macro_auroc_95ci": {"low": -0.01, "high": 0.03}, "conclusion": "NO_DIFFERENCE_SHOWN"}}),
                      encoding="utf-8")
    card = tmp_path / "card.md"
    card.write_text("# Synthetic test fixture\n", encoding="utf-8")
    model = {"model_id": "fixture_fusion", "display_name": "fixture_fusion", "task": "multilabel_ecg_classification", "status": "READY_UNVALIDATED",
             "validated": False, "research_inference": True, "inference_input": "ecg_12lead", "demographic_inputs": ["age_years", "sex"], "anatomy": "heart",
             "supported_modalities": ["ECG"], "supported_classes": [], "limitations": [],
             "artifact_bundle": {"dataset_version": "fixture", "dataset_license": "CC0 (synthetic test fixture)", "split_manifest_path": str(report),
                                 "task_definition": "fixture", "label_definition": {}, "preprocessing_version": "wfdb16-100hz-10s-leadstd-v1",
                                 "checkpoint_path": str(checkpoint), "checkpoint_sha256": hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
                                 "calibration": None, "decision_thresholds": None, "abstention_thresholds": None, "held_out_predictions_path": str(report),
                                 "evaluation_report_path": str(report), "model_card_path": str(card)}}
    path = tmp_path / "models.json"
    path.write_text(json.dumps({"schema_version": "1.0.0", "models": [model]}), encoding="utf-8")
    monkeypatch.setattr(model_registry, "REGISTRY_PATH", path)
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()
    yield model
    model_registry._load_registry.cache_clear()
    model_inference._load.cache_clear()


def _record(client, headers, pseudonym):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]
    header, data = _wfdb(_signal(), PTBXL_LEADS)
    ids = []
    for name, body, mime in (("rec.hea", header, "text/plain"), ("rec.dat", data, "application/octet-stream")):
        response = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (name, body, mime)}, data={"deidentified": "true"}, headers=headers)
        assert response.status_code == 201, response.text
        ids.append(response.json()["id"])
    return case_id, ids[0], ids[1]


def test_fusion_needs_age_and_sex_and_records_their_source(client, test_users, fusion_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id, header_id, signal_id = _record(client, headers, "CASE-ECG-FUSION")
    url = f"/api/v1/uploads/{header_id}/research-inference"
    body = {"model_id": "fixture_fusion", "declared_input_type": "ECG", "companion_upload_id": signal_id}

    refused = client.post(url, json=body, headers=headers)
    assert refused.status_code == 400 and refused.json()["detail"].startswith("DEMOGRAPHICS_REQUIRED")

    declared = client.post(url, json={**body, "age_years": 64, "sex": "F"}, headers=headers)
    assert declared.status_code == 201, declared.text
    used = declared.json()["research_output"]["demographic_inputs"]
    assert used["age_years"] == 64 and used["sex"] == "F" and used["sources"] == ["DECLARED_IN_REQUEST"]
    older = client.post(url, json={**body, "age_years": 85, "sex": "F"}, headers=headers).json()["research_output"]["classes"]
    assert [item["probability"] for item in older] != [item["probability"] for item in declared.json()["research_output"]["classes"]], "age reaches the network"

    reviewed = client.post(f"/api/v1/cases/{case_id}/demographics", json={"expected_revision": 0, "sex": "M", "date_of_birth": "1970-01-15",
                                                                          "source_file_id": None, "reason": "fixture attestation"}, headers=headers)
    assert reviewed.status_code == 201, reviewed.text
    from_case = client.post(url, json=body, headers=headers)
    assert from_case.status_code == 201, from_case.text
    used = from_case.json()["research_output"]["demographic_inputs"]
    assert used["sex"] == "M" and used["sources"] == ["REVIEWED_DEMOGRAPHICS_REVISION_1"]
    assert used["warnings"] and used["warnings"][0].startswith("AGE_FROM_REVIEWED_DATE_OF_BIRTH")

    listed = {item["model_id"]: item for item in client.get("/api/v1/research-models", headers=headers).json()["models"]}
    assert listed["fixture_fusion"]["demographic_inputs"] == ["age_years", "sex"]
    assert listed["fixture_fusion"]["held_out_evaluation"]["fusion_conclusion"] == "NO_DIFFERENCE_SHOWN"


def test_demographics_from_a_withdrawn_source_document_are_not_used(client, test_users, fusion_registry, db_session):
    from datetime import datetime, timezone

    from app.models.entities import UploadedFile

    headers = get_auth_headers(test_users["clinician_a"])
    case_id, header_id, signal_id = _record(client, headers, "CASE-ECG-FUSION-WITHDRAWN")
    reviewed = client.post(f"/api/v1/cases/{case_id}/demographics", json={"expected_revision": 0, "sex": "F", "date_of_birth": "1960-03-01",
                                                                          "source_file_id": signal_id, "reason": "fixture: read from a document"}, headers=headers)
    assert reviewed.status_code == 201, reviewed.text
    source = db_session.get(UploadedFile, signal_id)
    source.withdrawn_at = datetime.now(timezone.utc)
    db_session.commit()
    _case, header_id, signal_id = _record(client, headers, "CASE-ECG-FUSION-WITHDRAWN-2")  # a fresh record in another case
    body = {"model_id": "fixture_fusion", "declared_input_type": "ECG", "companion_upload_id": signal_id}
    other = client.post(f"/api/v1/uploads/{header_id}/research-inference", json=body, headers=headers)
    assert other.status_code == 400 and other.json()["detail"].startswith("DEMOGRAPHICS_REQUIRED"), "another case's demographics are never used"

    from app.services.model_inference import InferenceNotPermitted, resolve_demographics
    record = db_session.query(UploadedFile).filter(UploadedFile.case_id == case_id, UploadedFile.withdrawn_at.is_(None)).first()
    with pytest.raises(InferenceNotPermitted) as refusal:
        resolve_demographics(record, {}, db_session)
    assert "NOT_USED" in str(refusal.value), "a revision whose source document was withdrawn is not used"


def test_age_outside_the_request_range_is_rejected(client, test_users, fusion_registry):
    headers = get_auth_headers(test_users["clinician_a"])
    _case_id, header_id, signal_id = _record(client, headers, "CASE-ECG-FUSION-RANGE")
    response = client.post(f"/api/v1/uploads/{header_id}/research-inference",
                           json={"model_id": "fixture_fusion", "declared_input_type": "ECG", "companion_upload_id": signal_id, "age_years": 150, "sex": "F"},
                           headers=headers)
    assert response.status_code == 422
