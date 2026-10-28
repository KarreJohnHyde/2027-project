"""Patient and caregiver portal: own record only, reviewed results only, never the clinical API.
All accounts and reports are synthetic test fixtures."""

from app.models.entities import Finding, User, UserRole, VerificationStatus
from app.services.auth import get_password_hash
from tests.conftest import get_auth_headers

REPORT = b"SYNTHETIC PORTAL FIXTURE\nReport date: 2026-03-01\nHaemoglobin 13.2 g/dL (Reference range 12.0 - 15.5 g/dL)\n"


def _personal(db_session, username):
    user = User(username=username, email=f"{username}@test.medtwin", hashed_password=get_password_hash("PersonalPass1!"),
                full_name="Synthetic Person", role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED, is_active=True)
    db_session.add(user)
    db_session.commit()
    return user


def _case_with_report(client, clinician):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "PORTAL-CASE"}, headers=clinician).json()["id"]
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("labs.txt", REPORT, "text/plain")},
                         data={"deidentified": "true"}, headers=clinician).json()
    assert client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=clinician).status_code == 201
    return case_id, upload["id"]


def test_patient_sees_only_reviewed_results_and_never_the_clinical_api(client, db_session, test_users):
    clinician = get_auth_headers(test_users["clinician_a"])
    patient_user = _personal(db_session, "portal_patient")
    patient = get_auth_headers(patient_user)
    case_id, upload_id = _case_with_report(client, clinician)
    assert client.post(f"/api/v1/cases/{case_id}/members", json={"username": "clinician_b", "role": "PATIENT"}, headers=clinician).status_code == 400
    granted = client.post(f"/api/v1/cases/{case_id}/members", json={"username": "portal_patient", "role": "PATIENT"}, headers=clinician)
    assert granted.status_code == 201, granted.text

    assert client.get("/api/v1/portal/cases", headers=patient).json() == [{"case_id": case_id, "record": "PORTAL-CASE", "relationship": "PATIENT"}]
    before = client.get(f"/api/v1/portal/cases/{case_id}", headers=patient).json()
    assert before["results"] == [] and [document["id"] for document in before["documents"]] == [upload_id]

    finding = db_session.query(Finding).filter(Finding.case_id == case_id).one()
    assert client.post(f"/api/v1/reviews/{finding.id}", json={"review_status": "CONFIRMED"}, headers=clinician).status_code == 201
    after = client.get(f"/api/v1/portal/cases/{case_id}", headers=patient).json()
    assert [(item["name"], item["value"], item["unit"], item["reference_low"], item["reference_high"]) for item in after["results"]] == [
        ("Hemoglobin", 13.2, "g/dL", 12.0, 15.5)]
    assert after["results"][0]["reference_source"] == "PRINTED_ON_REPORT"
    download = client.get(f"/api/v1/portal/cases/{case_id}/documents/{upload_id}", headers=patient)
    assert download.status_code == 200 and download.content == REPORT

    # The portal link opens nothing clinical.
    assert client.get(f"/api/v1/cases/{case_id}", headers=patient).status_code == 403
    assert client.get(f"/api/v1/cases/{case_id}/measurements", headers=patient).status_code == 403
    assert all(item["id"] != case_id for item in client.get("/api/v1/cases", headers=patient).json())
    other_case = client.post("/api/v1/cases", json={"pseudonymous_id": "PORTAL-OTHER"}, headers=clinician).json()["id"]
    assert client.get(f"/api/v1/portal/cases/{other_case}", headers=patient).status_code == 404


def test_patient_manages_caregivers_and_caregivers_cannot_extend_access(client, db_session, test_users):
    clinician = get_auth_headers(test_users["clinician_a"])
    patient = get_auth_headers(_personal(db_session, "portal_patient2"))
    caregiver_user = _personal(db_session, "portal_caregiver")
    caregiver = get_auth_headers(caregiver_user)
    _personal(db_session, "portal_stranger")
    case_id, _ = _case_with_report(client, clinician)
    client.post(f"/api/v1/cases/{case_id}/members", json={"username": "portal_patient2", "role": "PATIENT"}, headers=clinician)

    assert client.get(f"/api/v1/portal/cases/{case_id}", headers=caregiver).status_code == 404
    added = client.post(f"/api/v1/portal/cases/{case_id}/caregivers", json={"username": "portal_caregiver"}, headers=patient)
    assert added.status_code == 201, added.text
    assert client.get(f"/api/v1/portal/cases/{case_id}", headers=caregiver).json()["relationship"] == "CAREGIVER"
    assert client.post(f"/api/v1/portal/cases/{case_id}/caregivers", json={"username": "portal_stranger"}, headers=caregiver).status_code == 403
    assert client.post(f"/api/v1/portal/cases/{case_id}/caregivers", json={"username": "clinician_a"}, headers=patient).status_code == 409
    assert [item["username"] for item in client.get(f"/api/v1/portal/cases/{case_id}/caregivers", headers=patient).json()] == ["portal_caregiver"]
    assert client.delete(f"/api/v1/portal/cases/{case_id}/caregivers/{caregiver_user.id}", headers=patient).status_code == 204
    assert client.get(f"/api/v1/portal/cases/{case_id}", headers=caregiver).status_code == 404
