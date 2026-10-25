"""
Unit and integration tests for new MedTwin backend endpoints and features:
- Persisted analysis-job status polling (/api/v1/analysis-jobs/{job_id})
- Upload association status update (/api/v1/uploads/{file_id}/association)
- Case statistics and statements (/api/v1/cases/{case_id}/stats, /statements)
- Case timeline (/api/v1/cases/{case_id}/timeline)
- Anatomical registration gate evaluation (/api/v1/anatomy/evaluate-registration)
- Multi-format authentication (JSON and form data)
"""

import pytest
from app.models.entities import Case, Examination, UploadedFile, ModalityType, InferenceRun, EvidenceStatus
from tests.conftest import get_auth_headers


def test_json_and_form_login_compatibility(client, test_users):
    """Verifies that login works seamlessly with both JSON and OAuth2 Form data."""
    # JSON login
    res_json = client.post("/api/v1/auth/login", json={"username": "clinician_a", "password": "ClinicianPass1!"})
    assert res_json.status_code == 200
    assert "access_token" in res_json.json()

    # Form login
    res_form = client.post("/api/v1/auth/login", data={"username": "clinician_a", "password": "ClinicianPass1!"})
    assert res_form.status_code == 200
    assert "access_token" in res_form.json()


def test_case_stats_and_statements_endpoints(client, db_session, test_users):
    """Verifies /api/v1/cases/{case_id}/stats and /api/v1/cases/{case_id}/statements."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    case = Case(
        pseudonymous_id="CASE-TEST-STATS-01",
        patient_ref="PATIENT-STATS",
        created_by_id=clinician.id
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    # Check stats on empty case
    res_stats = client.get(f"/api/v1/cases/{case.id}/stats", headers=headers)
    assert res_stats.status_code == 200
    data = res_stats.json()
    assert data["case_id"] == str(case.id)
    assert data["total_files"] == 0
    assert data["findings_count"] == 0

    # Check statements on empty case
    res_stmts = client.get(f"/api/v1/cases/{case.id}/statements", headers=headers)
    assert res_stmts.status_code == 200
    assert isinstance(res_stmts.json(), list)


def test_file_association_update_endpoint(client, db_session, test_users):
    """Verifies PATCH /api/v1/uploads/{file_id}/association."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    case = Case(
        pseudonymous_id="CASE-ASSOC-TEST-01",
        patient_ref="PATIENT-ASSOC",
        created_by_id=clinician.id
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    uf = UploadedFile(
        case_id=case.id,
        filename="wrist_xray.png",
        stored_filename="test_wrist.png",
        file_path="/tmp/test_wrist.png",
        file_hash="1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcdef",
        file_size_bytes=1024,
        mime_type="image/png",
        modality=ModalityType.IMAGE,
        is_associated=True,
        association_notes="Associated baseline"
    )
    db_session.add(uf)
    db_session.commit()
    db_session.refresh(uf)

    # Disassociate file
    patch_res = client.patch(
        f"/api/v1/uploads/{uf.id}/association",
        json={"is_associated": False, "association_notes": "Unrelated wrist scan from wrong accession"},
        headers=headers
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["is_associated"] is False
    assert "Unrelated wrist" in patch_res.json()["association_notes"]

    # Re-associate file
    patch_res2 = client.patch(
        f"/api/v1/uploads/{uf.id}/association",
        json={"is_associated": True, "association_notes": "Verified match"},
        headers=headers
    )
    assert patch_res2.status_code == 200
    assert patch_res2.json()["is_associated"] is True


def test_jobs_status_polling_endpoint(client, db_session, test_users):
    """Verifies GET /api/v1/analysis-jobs/{job_id}."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    case = Case(
        pseudonymous_id="CASE-JOB-TEST-01",
        patient_ref="PATIENT-JOB",
        created_by_id=clinician.id
    )
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    uf = UploadedFile(
        case_id=case.id,
        filename="test_ecg.csv",
        stored_filename="test_ecg.csv",
        file_path="/tmp/test_ecg.csv",
        file_hash="fedcba0987654321fedcba0987654321fedcba0987654321fedcba0987654321",
        file_size_bytes=2048,
        mime_type="text/csv",
        modality=ModalityType.ECG,
        is_associated=True
    )
    db_session.add(uf)
    db_session.commit()
    db_session.refresh(uf)

    job = InferenceRun(
        case_id=case.id,
        file_id=uf.id,
        modality=ModalityType.ECG,
        model_name="1D-CNN-ECG-Classifier",
        model_version="v1.0.0",
        preprocessing_version="0.5-45Hz-Bandpass",
        status=EvidenceStatus.COMPLETED,
        execution_time_ms=145.2
    )
    db_session.add(job)
    db_session.commit()
    db_session.refresh(job)

    res = client.get(f"/api/v1/analysis-jobs/{job.id}", headers=headers)
    assert res.status_code == 200
    data = res.json()
    assert data["id"] == job.id
    assert data["upload_id"] == uf.id
    assert data["status"] == "COMPLETED"
    assert data["execution_time_ms"] == 145.2


def test_anatomy_evaluate_registration_endpoint(client, test_users):
    """Synthetic registration tests math without granting a patient L2 mapping."""
    clinician = test_users["clinician_a"]
    headers = get_auth_headers(clinician)

    # 1. Synthetic fixture can pass its mathematical gate but remains L1
    res_pass = client.post(
        "/api/v1/anatomy/evaluate-registration",
        json={"tau_tre_threshold": 5.0, "simulate_high_error": False},
        headers=headers
    )
    assert res_pass.status_code == 200
    data_pass = res_pass.json()
    assert data_pass["status"] == "SYNTHETIC_MATH_PASSED_L1_ONLY"
    assert data_pass["registration_quality_passed"] is True
    assert data_pass["is_gate_passed"] is False
    assert data_pass["anatomical_level"] == "L1_GENERIC"
    assert data_pass["assigned_region"] is None

    # 2. Simulated high error should reject gate and revert to L1 Generic with region null
    res_fail = client.post(
        "/api/v1/anatomy/evaluate-registration",
        json={"tau_tre_threshold": 5.0, "simulate_high_error": True},
        headers=headers
    )
    assert res_fail.status_code == 200
    data_fail = res_fail.json()
    assert data_fail["status"] == "SYNTHETIC_FIXTURE_REJECTED"
    assert data_fail["is_gate_passed"] is False
    assert data_fail["anatomical_level"] == "L1_GENERIC"
    assert data_fail["assigned_region"] is None
    assert "Synthetic code fixture failed" in data_fail["message"]
