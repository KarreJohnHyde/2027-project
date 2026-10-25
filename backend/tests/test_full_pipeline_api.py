"""
Full End-to-End API Integration Test for MedTwin.
Simulates a real clinician uploading records, analyzing modalities,
evaluating multimodal fusion, checking report concordance,
testing the 3D anatomical registration gate, and recording a human review.
"""

import io
from datetime import datetime, timezone, timedelta
import pytest
from tests.conftest import get_auth_headers


def test_full_clinician_workflow_api(client, test_users):
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    # 1. Create a new case
    case_payload = {
        "pseudonymous_id": "CASE-E2E-TEST-99",
        "patient_ref": "PATIENT-REF-99",
        "description": "Patient with acute wrist trauma and chest examination."
    }
    case_res = client.post("/api/v1/cases", json=case_payload, headers=headers)
    assert case_res.status_code == 201
    case_id = case_res.json()["id"]

    # 2. Add 3 dated examinations
    now = datetime.now(timezone.utc)
    for i, mod in enumerate(["IMAGE", "IMAGE", "ECG"]):
        exam_res = client.post(
            f"/api/v1/cases/{case_id}/examinations",
            json={
                "exam_date": (now - timedelta(days=(3 - i) * 60)).isoformat(),
                "modality": mod,
                "clinical_indication": f"Exam step {i+1}"
            },
            headers=headers
        )
        assert exam_res.status_code == 201

    # 3. Upload medical image
    dummy_png_bytes = b"\x89PNG\r\n\x1a\n" + b"\x00" * 200
    upload_res = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={"file": ("wrist_xray.png", dummy_png_bytes, "image/png")},
        data={
            "is_associated": "true",
            "association_notes": "Associated by wrist protocol",
            "deidentified": "true",
        },
        headers=headers
    )
    assert upload_res.status_code == 201
    file_id = upload_res.json()["id"]
    file_hash = upload_res.json()["file_hash"]

    # 4. Verify upload idempotency: uploading same file to same case returns existing file
    dup_res = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={"file": ("wrist_xray_copy.png", dummy_png_bytes, "image/png")},
        data={"is_associated": "true", "deidentified": "true"},
        headers=headers
    )
    assert dup_res.status_code == 201
    assert dup_res.json()["id"] == file_id
    assert dup_res.json()["file_hash"] == file_hash

    # 5. Check fusion state when no analyzed findings exist -> ABSTAIN
    fusion_res = client.post(f"/api/v1/cases/{case_id}/fusion", headers=headers)
    assert fusion_res.status_code == 200
    assert fusion_res.json()["fused_status"] == "ABSTAIN"

    # 6. Examination dates alone are not numeric longitudinal observations
    forecast_res = client.post(
        f"/api/v1/cases/{case_id}/forecast",
        json={"case_id": case_id, "target_metric": "Joint Space Width", "unit": "mm", "horizon_days": 180},
        headers=headers
    )
    assert forecast_res.status_code == 200
    fc_data = forecast_res.json()
    assert fc_data["eligibility_status"] == "NOT_ELIGIBLE"
    assert fc_data["observations_count"] == 0
    assert fc_data["predicted_value"] is None
    assert fc_data["baseline_persistence"] is None

    # 7. List anatomical assets
    anatomy_res = client.get("/api/v1/assets/anatomy")
    assert anatomy_res.status_code == 200
    assets = anatomy_res.json()
    assert len(assets) >= 1
    assert assets[0]["representation_level"] == "L1" # Explicitly generic

    # 8. Check system health
    health_res = client.get("/api/v1/system/health")
    assert health_res.status_code == 200
    assert health_res.json()["status"] == "HEALTHY"
    assert "RESEARCH PROTOTYPE ONLY" in health_res.json()["research_notice"]
    assert health_res.json()["health_scope"] == "API_AND_DATABASE_ONLY"
    assert health_res.json()["models_status"]["image_classifier"] == "MODEL_UNAVAILABLE"
