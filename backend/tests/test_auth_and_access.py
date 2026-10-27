"""
Security & Authorization Tests for MedTwin.
Verifies role-based access control, cross-case data leakage prevention,
and audit trail privacy preservation.
"""

import pytest
from sqlalchemy import create_engine, inspect, text

from app.models.entities import (
    AuditEvent,
    Case,
    EvidenceStatus,
    Finding,
    InferenceRun,
    ModalityType,
    UploadedFile,
    User,
    UserRole,
    VerificationStatus,
)
from app.services.auth import get_password_hash
from app.services.audit_service import log_audit_event
from tests.conftest import get_auth_headers


def test_user_registration_and_login(client):
    # 1. Register new user
    reg_payload = {
        "username": "dr_watson",
        "email": "watson@bakerstreet.med",
        "password": "Password123!",
        "full_name": "Dr. John Watson"
    }
    res = client.post("/api/v1/auth/register", json=reg_payload)
    assert res.status_code == 201
    data = res.json()
    assert data["username"] == "dr_watson"
    assert data["role"] == "public"
    assert data["verification_status"] == "UNVERIFIED"
    assert "hashed_password" not in data

    # 2. Login with credentials
    login_res = client.post("/api/v1/auth/login", data={"username": "dr_watson", "password": "Password123!"})
    assert login_res.status_code == 200
    token_data = login_res.json()
    assert "access_token" in token_data
    assert token_data["token_type"] == "bearer"
    assert token_data["role"] == "public"
    assert token_data["verification_status"] == "UNVERIFIED"

    email_login = client.post(
        "/api/v1/auth/login",
        json={"username": "WATSON@BAKERSTREET.MED", "password": "Password123!"},
    )
    assert email_login.status_code == 200
    assert email_login.json()["username"] == "dr_watson"


def test_public_registration_cannot_self_assign_privileged_role(client):
    res = client.post(
        "/api/v1/auth/register",
        json={
            "username": "role_escalation_attempt",
            "email": "role-escalation@test.medtwin",
            "password": "Password123!",
            "role": "admin",
        },
    )

    assert res.status_code == 422
    assert any(
        error.get("loc", [])[-1:] == ["role"]
        for error in res.json().get("detail", [])
    )


def test_registration_records_requested_role_without_granting_privileges(client, db_session):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "department_expert",
            "email": "department-expert@test.medtwin",
            "password": "Password123!",
            "requested_role": "department_expert",
            "requested_department": "cardiology",
        },
    )

    assert registration.status_code == 201, registration.text
    assert registration.json()["role"] == "public"
    assert registration.json()["verification_status"] == "UNVERIFIED"

    event = (
        db_session.query(AuditEvent)
        .filter_by(action="USER_REGISTERED", resource_id=str(registration.json()["id"]))
        .one()
    )
    assert event.details["requested_role"] == "department_expert"
    assert event.details["requested_department"] == "cardiology"
    assert event.details["role"] == "public"


@pytest.mark.parametrize("requested_role", ["doctor", "surgeon", "department_expert"])
def test_professional_profile_requires_department(client, requested_role):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": f"missing_department_{requested_role}",
            "email": f"missing-department-{requested_role}@test.medtwin",
            "password": "Password123!",
            "requested_role": requested_role,
        },
    )

    assert registration.status_code == 422
    assert "Select a hospital department" in str(registration.json()["detail"])


def test_other_department_requires_name(client):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "other_department",
            "email": "other-department@test.medtwin",
            "password": "Password123!",
            "requested_role": "surgeon",
            "requested_department": "other",
        },
    )

    assert registration.status_code == 422
    assert "Enter the name of the other department" in str(registration.json()["detail"])


def test_public_registrant_cannot_review_or_mutate_clinical_catalog(client, db_session):
    registration = client.post(
        "/api/v1/auth/register",
        json={
            "username": "public_account",
            "email": "public-account@test.medtwin",
            "password": "Password123!",
        },
    )
    assert registration.status_code == 201, registration.text

    login = client.post(
        "/api/v1/auth/login",
        json={"username": "public_account", "password": "Password123!"},
    )
    assert login.status_code == 200, login.text
    headers = {"Authorization": f"Bearer {login.json()['access_token']}"}

    case_response = client.post(
        "/api/v1/cases",
        json={"pseudonymous_id": "CASE-PUBLIC-RBAC"},
        headers=headers,
    )
    assert case_response.status_code == 201, case_response.text
    case_id = case_response.json()["id"]

    finding = Finding(
        case_id=case_id,
        modality=ModalityType.REPORT,
        category="Synthetic authorization fixture",
        label="No clinical assertion",
        mapping_status="UNASSOCIATED",
        is_demo=False,
    )
    db_session.add(finding)
    db_session.commit()
    db_session.refresh(finding)

    review = client.post(
        f"/api/v1/reviews/{finding.id}",
        json={"review_status": "CONFIRMED"},
        headers=headers,
    )
    order = client.post(
        f"/api/v1/cases/{case_id}/orders",
        json={"item_id": "PKG-GEN-01"},
        headers=headers,
    )
    lab_report = client.post(
        f"/api/v1/cases/{case_id}/lab-reports",
        json={"results": [{"code": "NA", "value": 140.0}]},
        headers=headers,
    )

    assert review.status_code == 403
    assert order.status_code == 403
    assert lab_report.status_code == 403


def test_unverified_clinician_role_is_not_sufficient_for_privileged_access(
    client, db_session
):
    user = User(
        username="unverified_clinician",
        email="unverified-clinician@test.medtwin",
        hashed_password=get_password_hash("Password123!"),
        role=UserRole.CLINICIAN,
        verification_status=VerificationStatus.UNVERIFIED,
        is_active=True,
    )
    db_session.add(user)
    db_session.commit()
    db_session.refresh(user)

    case = Case(pseudonymous_id="CASE-UNVERIFIED-CLINICIAN", created_by_id=user.id)
    db_session.add(case)
    db_session.commit()
    db_session.refresh(case)

    response = client.post(
        f"/api/v1/cases/{case.id}/orders",
        json={"item_id": "PKG-GEN-01"},
        headers=get_auth_headers(user),
    )

    assert response.status_code == 403
    assert response.json()["detail"] == "Professional privileges require a verified account."


def test_verification_migration_marks_legacy_users_unverified():
    from app.migrations import run_migrations

    legacy_engine = create_engine("sqlite:///:memory:")
    with legacy_engine.begin() as connection:
        connection.execute(text(
            "CREATE TABLE users ("
            "id INTEGER PRIMARY KEY, username VARCHAR(64) NOT NULL, role VARCHAR(16) NOT NULL)"
        ))
        connection.execute(text(
            "INSERT INTO users (id, username, role) VALUES (1, 'legacy_clinician', 'CLINICIAN')"
        ))

    run_migrations(legacy_engine)

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("users")}
    assert "verification_status" in columns
    with legacy_engine.connect() as connection:
        status_value = connection.execute(
            text("SELECT verification_status FROM users WHERE id = 1")
        ).scalar_one()
    assert status_value == "UNVERIFIED"


def test_cross_case_access_isolation(client, db_session, test_users):
    """
    CRITICAL SECURITY TEST:
    A clinician MUST NOT be allowed to access another clinician's private case.
    Admin MUST be allowed to access any case.
    """
    user_a = test_users["clinician_a"]
    user_b = test_users["clinician_b"]
    admin = test_users["admin"]

    # Clinician A creates Case 1
    case_a = Case(
        pseudonymous_id="CASE-SEC-001",
        patient_ref="PATIENT-ALPHA",
        created_by_id=user_a.id
    )
    db_session.add(case_a)
    db_session.commit()
    db_session.refresh(case_a)

    headers_a = get_auth_headers(user_a)
    headers_b = get_auth_headers(user_b)
    headers_admin = get_auth_headers(admin)

    # 1. Clinician A accesses own case -> Allowed (200)
    res_a = client.get(f"/api/v1/cases/{case_a.id}", headers=headers_a)
    assert res_a.status_code == 200
    assert res_a.json()["pseudonymous_id"] == "CASE-SEC-001"

    # 2. Clinician B tries to access Clinician A's case -> FORBIDDEN (403)
    res_b = client.get(f"/api/v1/cases/{case_a.id}", headers=headers_b)
    assert res_b.status_code == 403
    assert "Access denied" in res_b.json()["detail"]

    # 3. Admin accesses Case A -> Allowed (200)
    res_admin = client.get(f"/api/v1/cases/{case_a.id}", headers=headers_admin)
    assert res_admin.status_code == 200


def test_cross_case_upload_job_and_provenance_isolation(client, db_session, test_users):
    owner = test_users["clinician_a"]
    other = test_users["clinician_b"]
    case = Case(pseudonymous_id="CASE-RESOURCE-ISOLATION", created_by_id=owner.id)
    db_session.add(case)
    db_session.flush()
    upload = UploadedFile(
        case_id=case.id,
        filename="deidentified.txt",
        stored_filename=f"{'b' * 64}.txt",
        file_path="unused-for-metadata-test",
        file_hash="b" * 64,
        file_size_bytes=12,
        mime_type="text/plain",
        modality=ModalityType.REPORT,
        is_associated=True,
    )
    db_session.add(upload)
    db_session.flush()
    job = InferenceRun(
        case_id=case.id,
        file_id=upload.id,
        modality=ModalityType.REPORT,
        model_name="Rule-Based Clinical Text Baseline",
        model_version="rules-v1.0.0",
        preprocessing_version="test",
        status=EvidenceStatus.COMPLETED,
    )
    db_session.add(job)
    db_session.commit()

    other_headers = get_auth_headers(other)
    assert client.get(f"/api/v1/uploads/{upload.id}", headers=other_headers).status_code == 403
    assert client.get(f"/api/v1/analysis-jobs/{job.id}", headers=other_headers).status_code == 403
    assert client.get(
        f"/api/v1/cases/{case.id}/provenance", headers=other_headers
    ).status_code == 403


def test_audit_logging_sanitizes_clinical_text(db_session, test_users):
    """
    Verifies that narrative clinical text is redacted from audit logs.
    """
    user = test_users["clinician_a"]
    sensitive_details = {
        "patient_name": "John Doe",
        "report_text": "Patient has acute compound fracture with severe pain.",
        "case_id": 101,
        "modality": "REPORT"
    }

    log_audit_event(
        db=db_session,
        action="REPORT_ACCESSED",
        resource_type="REPORT",
        resource_id="101",
        user=user,
        details=sensitive_details
    )

    # Inspect stored audit event
    audit_entry = db_session.query(AuditEvent).filter(AuditEvent.action == "REPORT_ACCESSED").first()
    assert audit_entry is not None
    assert "John Doe" not in str(audit_entry.details)
    assert "Patient has acute compound fracture" not in str(audit_entry.details)
    assert "[REDACTED_FOR_PRIVACY" in audit_entry.details["report_text"]
    assert audit_entry.details["case_id"] == 101


def test_audit_logging_redacts_free_form_file_metadata(db_session, test_users):
    user = test_users["clinician_a"]
    log_audit_event(
        db=db_session,
        action="FILE_UPLOADED",
        resource_type="FILE",
        resource_id="202",
        user=user,
        details={
            "case_id": 101,
            "filename": "Jane_Doe_cardiology_report.txt",
            "association_notes": "Jane Doe reported chest pain.",
            "file_hash": "a" * 64,
        },
    )

    event = db_session.query(AuditEvent).filter(AuditEvent.resource_id == "202").one()
    assert "Jane_Doe" not in event.details["filename"]
    assert "Jane Doe" not in event.details["association_notes"]
    assert event.details["file_hash"] == "a" * 64


def test_longitudinal_comparison_enforces_case_ownership(client, db_session, test_users):
    owner = test_users["clinician_a"]
    other = test_users["clinician_b"]
    case = Case(pseudonymous_id="CASE-COMPARE-ISOLATION", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()

    response = client.post(
        f"/api/v1/cases/{case.id}/compare",
        json={},
        headers=get_auth_headers(other),
    )
    assert response.status_code == 403


def test_global_audit_is_admin_only(client, test_users):
    clinician_response = client.get(
        "/api/v1/system/audit",
        headers=get_auth_headers(test_users["clinician_a"]),
    )
    assert clinician_response.status_code == 403

    admin_response = client.get(
        "/api/v1/system/audit",
        headers=get_auth_headers(test_users["admin"]),
    )
    assert admin_response.status_code == 200


def test_synthetic_registration_cannot_poison_another_case_provenance(
    client, db_session, test_users
):
    owner = test_users["clinician_a"]
    other = test_users["clinician_b"]
    case = Case(pseudonymous_id="CASE-PROVENANCE-ISOLATION", created_by_id=owner.id)
    db_session.add(case)
    db_session.commit()

    response = client.post(
        "/api/v1/anatomy/evaluate-registration",
        json={"case_id": case.id},
        headers=get_auth_headers(other),
    )
    assert response.status_code == 403

    provenance = client.get(
        f"/api/v1/cases/{case.id}/provenance",
        headers=get_auth_headers(owner),
    )
    assert provenance.status_code == 200
    assert all(
        event["action"] != "REGISTRATION_GATE_EVALUATED"
        for event in provenance.json()
    )
