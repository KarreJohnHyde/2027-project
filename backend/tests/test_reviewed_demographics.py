"""Synthetic reviewer context; no report/header or laboratory value is overwritten."""
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import IntegrityError

from app.models.entities import AuditEvent, Case, CaseMembership, ModalityType, ReviewedDemographics, UploadedFile, UserRole, VerificationStatus
from conftest import get_auth_headers


@pytest.fixture
def demographic_case(db_session, test_users):
    row = Case(pseudonymous_id="SYNTHETIC-CONTEXT", created_by_id=test_users["clinician_a"].id)
    db_session.add(row)
    db_session.commit()
    return row


def payload(**changes):
    return {"expected_revision": 0, "sex": "UNKNOWN", "date_of_birth": None,
            "source_file_id": None, "reason": "Synthetic review context for regression testing", **changes}


def endpoint(case):
    return f"/api/v1/cases/{case.id}/demographics"


def test_append_revision_clear_and_private_audit(client, db_session, test_users, demographic_case):
    headers = get_auth_headers(test_users["clinician_a"])
    url = endpoint(demographic_case)
    initial = client.get(url, headers=headers).json()
    assert initial["current"] is None and initial["can_record"] is True
    first = client.post(url, headers=headers, json=payload(sex="F", date_of_birth="1988-04-03"))
    assert first.status_code == 201, first.text
    assert first.json()["revision"] == 1
    assert first.json()["provenance"] == "REVIEWER_ENTERED_NOT_SOURCE_EXTRACTED"
    assert first.json()["source_state"] == "REVIEWER_ATTESTATION"
    assert first.json()["source_reference_id"] is None
    cleared = client.post(url, headers=headers, json=payload(expected_revision=1, reason="Clear incorrect synthetic context"))
    assert cleared.status_code == 201
    history = client.get(url, headers=headers).json()
    assert history["current"]["date_of_birth"] is None
    assert history["current"]["sex"] == "UNKNOWN"
    assert history["history"][1]["date_of_birth"] == "1988-04-03"
    events = db_session.query(AuditEvent).filter_by(action="DEMOGRAPHIC_CONTEXT_RECORDED").all()
    assert len(events) == 2
    assert set(events[0].details) <= {"case_id", "revision", "source_file_id", "request_id"}
    assert "1988" not in str(events[0].details)
    assert "Synthetic review context" not in str(events[0].details)


def test_stale_revision_is_rejected_without_extra_history(client, db_session, test_users, demographic_case):
    headers = get_auth_headers(test_users["clinician_a"])
    assert client.post(endpoint(demographic_case), headers=headers, json=payload()).status_code == 201
    assert client.post(endpoint(demographic_case), headers=headers, json=payload()).status_code == 409
    assert db_session.query(ReviewedDemographics).count() == 1


@pytest.mark.parametrize("changes", [
    {"date_of_birth": (date.today() + timedelta(days=1)).isoformat()},
    {"date_of_birth": "not-a-date"}, {"sex": "guessed"}, {"reason": "   "},
    {"expected_revision": -1}, {"source_file_id": -1}, {"unexpected_field": True},
])
def test_invalid_context_rejected(client, test_users, demographic_case, changes):
    response = client.post(endpoint(demographic_case), headers=get_auth_headers(test_users["clinician_a"]), json=payload(**changes))
    assert response.status_code == 422


def test_case_scope_and_review_role_enforced(client, db_session, test_users, demographic_case):
    url = endpoint(demographic_case)
    other = test_users["clinician_b"]
    assert client.get(url, headers=get_auth_headers(other)).status_code == 403
    assert client.post(url, headers=get_auth_headers(other), json=payload()).status_code == 403
    owner = test_users["clinician_a"]
    owner.role = UserRole.PUBLIC
    owner.verification_status = VerificationStatus.UNVERIFIED
    db_session.commit()
    public_read = client.get(url, headers=get_auth_headers(owner))
    assert public_read.status_code == 200 and public_read.json()["can_record"] is False
    assert client.post(url, headers=get_auth_headers(owner), json=payload()).status_code == 403
    owner.role = UserRole.CLINICIAN
    db_session.commit()
    assert client.get(url, headers=get_auth_headers(owner)).json()["can_record"] is False
    assert client.post(url, headers=get_auth_headers(owner), json=payload()).status_code == 403


def test_viewer_can_read_but_not_record(client, db_session, test_users, demographic_case):
    viewer = test_users["clinician_b"]
    db_session.add(CaseMembership(case_id=demographic_case.id, user_id=viewer.id, role="VIEWER", granted_by_id=test_users["clinician_a"].id))
    db_session.commit()
    response = client.get(endpoint(demographic_case), headers=get_auth_headers(viewer))
    assert response.status_code == 200 and response.json()["can_record"] is False
    assert client.post(endpoint(demographic_case), headers=get_auth_headers(viewer), json=payload()).status_code == 403


def test_source_must_be_active_and_in_case(client, db_session, test_users, demographic_case):
    headers = get_auth_headers(test_users["clinician_a"])
    assert client.post(endpoint(demographic_case), headers=headers, json=payload(source_file_id=999999)).status_code == 404
    source = UploadedFile(case_id=demographic_case.id, filename="synthetic.txt", stored_filename="synthetic.txt",
                          file_path="synthetic.txt", file_hash="f" * 64, file_size_bytes=1,
                          mime_type="text/plain", modality=ModalityType.REPORT, is_associated=True)
    db_session.add(source)
    db_session.commit()
    first = client.post(endpoint(demographic_case), headers=headers, json=payload(source_file_id=source.id))
    assert first.status_code == 201
    assert first.json()["source_state"] == "ACTIVE"
    source.is_associated = False
    db_session.commit()
    assert client.get(endpoint(demographic_case), headers=headers).json()["current"]["source_state"] == "WITHDRAWN_OR_UNASSOCIATED"
    assert client.post(endpoint(demographic_case), headers=headers, json=payload(expected_revision=1, source_file_id=source.id)).status_code == 409
    other = Case(pseudonymous_id="SYNTHETIC-OTHER", created_by_id=test_users["clinician_a"].id)
    db_session.add(other)
    db_session.commit()
    assert client.post(endpoint(other), headers=headers, json=payload(source_file_id=source.id)).status_code == 404


def test_case_deletion_cascades_review_context(client, db_session, test_users, demographic_case):
    headers = get_auth_headers(test_users["clinician_a"])
    assert client.post(endpoint(demographic_case), headers=headers, json=payload()).status_code == 201
    assert client.delete(f"/api/v1/cases/{demographic_case.id}", headers=headers).status_code == 204
    assert db_session.query(ReviewedDemographics).count() == 0


def test_demographic_context_requires_authentication(client, demographic_case):
    assert client.get(endpoint(demographic_case)).status_code == 401
    assert client.post(endpoint(demographic_case), json=payload()).status_code == 401


def test_verified_editor_can_record_context(client, db_session, test_users, demographic_case):
    editor = test_users["clinician_b"]
    db_session.add(CaseMembership(case_id=demographic_case.id, user_id=editor.id, role="EDITOR", granted_by_id=test_users["clinician_a"].id))
    db_session.commit()
    headers = get_auth_headers(editor)
    assert client.get(endpoint(demographic_case), headers=headers).json()["can_record"] is True
    assert client.post(endpoint(demographic_case), headers=headers, json=payload()).status_code == 201


@pytest.mark.parametrize("source_change", ["withdraw", "supersede", "delete"])
def test_source_provenance_survives_lifecycle_changes(client, db_session, test_users, demographic_case, source_change):
    source = UploadedFile(case_id=demographic_case.id, filename="synthetic.txt", stored_filename="synthetic.txt",
                          file_path="synthetic.txt", file_hash="a" * 64, file_size_bytes=1,
                          mime_type="text/plain", modality=ModalityType.REPORT, is_associated=True)
    db_session.add(source)
    db_session.commit()
    source_id = source.id
    headers = get_auth_headers(test_users["clinician_a"])
    url = endpoint(demographic_case)
    first = client.post(url, headers=headers, json=payload(source_file_id=source_id))
    assert first.status_code == 201 and first.json()["source_reference_id"] == source_id
    if source_change == "delete":
        db_session.delete(source)
    elif source_change == "withdraw":
        source.withdrawn_at = datetime.now(timezone.utc)
    else:
        source.superseded_by_file_id = source.id  # Synthetic lifecycle marker; no replacement bytes needed.
    db_session.commit()
    current = client.get(url, headers=headers).json()["current"]
    assert current["source_reference_id"] == source_id
    assert current["source_state"] == ("SOURCE_DELETED" if source_change == "delete" else "WITHDRAWN_OR_UNASSOCIATED")
    if source_change == "delete":
        assert current["source_file_id"] is None
    else:
        assert client.post(url, headers=headers, json=payload(expected_revision=1, source_file_id=source_id)).status_code == 409


def test_legacy_missing_source_is_not_falsely_called_attestation(client, db_session, test_users, demographic_case):
    row = ReviewedDemographics(case_id=demographic_case.id, revision=1, sex="UNKNOWN", reason="Legacy synthetic context",
                               reviewed_by_id=test_users["clinician_a"].id)
    db_session.add(row)
    db_session.commit()
    current = client.get(endpoint(demographic_case), headers=get_auth_headers(test_users["clinician_a"])).json()["current"]
    assert current["source_state"] == "PROVENANCE_UNAVAILABLE"


def test_database_unique_revision_guards_competing_writes(client, db_session, test_users, demographic_case):
    headers = get_auth_headers(test_users["clinician_a"])
    assert client.post(endpoint(demographic_case), headers=headers, json=payload()).status_code == 201
    with pytest.raises(IntegrityError), db_session.begin_nested():
        db_session.add(ReviewedDemographics(case_id=demographic_case.id, revision=1, sex="UNKNOWN",
                                          reason="Competing synthetic write", reviewed_by_id=test_users["clinician_a"].id))
        db_session.flush()
    assert db_session.query(ReviewedDemographics).count() == 1
    assert db_session.query(AuditEvent).filter_by(action="DEMOGRAPHIC_CONTEXT_RECORDED").count() == 1


def test_source_provenance_migration_is_idempotent_and_does_not_guess():
    from app.migrations import run_migrations

    engine = create_engine("sqlite:///:memory:")
    try:
        with engine.begin() as connection:
            connection.execute(text("CREATE TABLE reviewed_demographics (id INTEGER PRIMARY KEY, source_file_id INTEGER)"))
            connection.execute(text("INSERT INTO reviewed_demographics VALUES (1, 42), (2, NULL)"))
        run_migrations(engine)
        assert run_migrations(engine) == []
        with engine.connect() as connection:
            rows = connection.execute(text("SELECT source_reference_id, source_kind FROM reviewed_demographics ORDER BY id")).all()
        assert rows == [(42, "FILE"), (None, None)]
    finally:
        engine.dispose()
