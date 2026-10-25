"""Phase 1 acceptance test: upload -> hash -> process -> reload persisted evidence."""

import hashlib

from tests.conftest import get_auth_headers


def test_upload_requires_explicit_deidentified_attestation(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-DEID-ATTESTATION"},
        headers=headers,
    )
    case_id = case_response.json()["id"]
    file_payload = {
        "file": ("report.txt", b"No pleural effusion.", "text/plain")
    }

    missing = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files=file_payload,
        headers=headers,
    )
    assert missing.status_code == 400

    rejected = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files=file_payload,
        data={"deidentified": "false"},
        headers=headers,
    )
    assert rejected.status_code == 400

    assert client.get(
        f"/api/v1/cases/{case_id}/uploads", headers=headers
    ).json() == []


def test_deidentified_document_persists_evidence_and_provenance(client, test_users):
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    case_response = client.post(
        "/api/v1/cases",
        json={
            "pseudonymous_id": "CASE-PHASE1-GATE-001",
            "description": "De-identified document-processing acceptance case.",
        },
        headers=headers,
    )
    assert case_response.status_code == 201
    case_id = case_response.json()["id"]

    report_bytes = (
        b"RADIOLOGY REPORT\n"
        b"FINDINGS: No pleural effusion or pneumothorax. Prior fracture is chronic.\n"
        b"IMPRESSION: Normal sinus rhythm.\n"
    )
    expected_sha256 = hashlib.sha256(report_bytes).hexdigest()

    upload_response = client.post(
        f"/api/v1/cases/{case_id}/uploads",
        files={"file": ("deidentified_report.txt", report_bytes, "text/plain")},
        data={"is_associated": "true", "deidentified": "true"},
        headers=headers,
    )
    assert upload_response.status_code == 201
    upload = upload_response.json()
    assert upload["file_hash"] == expected_sha256
    assert len(upload["file_hash"]) == 64

    job_response = client.post(
        f"/api/v1/uploads/{upload['id']}/analysis-jobs",
        headers=headers,
    )
    assert job_response.status_code == 201
    job = job_response.json()
    assert job["upload_id"] == upload["id"]
    assert job["status"] == "COMPLETED"
    assert job["model_name"] == "Rule-Based Clinical Text Baseline"
    assert job["findings"]
    assert job["findings"][0]["review_status"] == "PENDING_HUMAN_REVIEW"

    # These reads are the same contract used after a browser/application reload.
    reloaded_uploads = client.get(
        f"/api/v1/cases/{case_id}/uploads", headers=headers
    ).json()
    reloaded_jobs = client.get(
        f"/api/v1/cases/{case_id}/analysis-jobs", headers=headers
    ).json()
    reloaded_findings = client.get(
        f"/api/v1/cases/{case_id}/findings", headers=headers
    ).json()
    reloaded_provenance = client.get(
        f"/api/v1/cases/{case_id}/provenance", headers=headers
    ).json()

    assert reloaded_uploads[0]["file_hash"] == expected_sha256
    assert reloaded_jobs[0]["id"] == job["id"]
    assert reloaded_jobs[0]["upload_id"] == upload["id"]
    assert reloaded_findings[0]["evidence_provenance"]["input_hash"] == expected_sha256
    assert reloaded_findings[0]["report_statements"]

    actions = {event["action"] for event in reloaded_provenance}
    assert "FILE_UPLOADED" in actions
    assert "ANALYSIS_JOB_COMPLETED" in actions
