"""Case-erasure tests for database rows and content-addressed upload objects."""

from pathlib import Path

from app.models.entities import (
    AuditEvent,
    Case,
    CaseMembership,
    ModalityType,
    UploadedFile,
)
from app.services import upload_store
from conftest import get_auth_headers


def _case(db_session, owner, pseudonym: str) -> Case:
    record = Case(pseudonymous_id=pseudonym, created_by_id=owner.id)
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def _file(db_session, case: Case, path: Path, stored_filename: str = "a" * 64 + ".txt") -> UploadedFile:
    record = UploadedFile(
        case_id=case.id,
        filename="deidentified.txt",
        stored_filename=stored_filename,
        file_path=str(path),
        file_hash="a" * 64,
        file_size_bytes=path.stat().st_size if path.exists() else 1,
        mime_type="text/plain",
        modality=ModalityType.REPORT,
    )
    db_session.add(record)
    db_session.commit()
    db_session.refresh(record)
    return record


def _use_upload_root(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "uploads"
    root.mkdir()
    monkeypatch.setattr(upload_store.config, "UPLOAD_DIR", root)
    return root


def test_case_erasure_removes_unique_managed_object_and_audits_metadata(
    client, db_session, test_users, monkeypatch, tmp_path
):
    root = _use_upload_root(monkeypatch, tmp_path)
    owner = test_users["clinician_a"]
    case = _case(db_session, owner, "ERASE-UNIQUE")
    stored_filename = "a" * 64 + ".txt"
    target = root / stored_filename
    target.write_bytes(b"deidentified fixture")
    file_record = _file(db_session, case, target, stored_filename)

    response = client.delete(f"/api/v1/cases/{case.id}", headers=get_auth_headers(owner))

    assert response.status_code == 204
    assert not target.exists()
    assert db_session.query(Case).filter(Case.id == case.id).first() is None
    assert db_session.query(UploadedFile).filter(UploadedFile.id == file_record.id).first() is None
    event = db_session.query(AuditEvent).filter(AuditEvent.action == "CASE_DELETED").order_by(AuditEvent.id.desc()).first()
    expected_details = {
        "retention_action": "CASE_ERASURE",
        "stored_objects_deleted": 1,
        "stored_objects_missing": 0,
        "stored_objects_preserved_shared": 0,
        "stored_object_cleanup_errors": 0,
    }
    assert {key: event.details[key] for key in expected_details} == expected_details
    assert event.details["request_id"] == response.headers["X-Request-ID"]


def test_case_erasure_preserves_shared_object_until_final_reference_is_deleted(
    client, db_session, test_users, monkeypatch, tmp_path
):
    root = _use_upload_root(monkeypatch, tmp_path)
    owner = test_users["clinician_a"]
    first = _case(db_session, owner, "ERASE-SHARED-A")
    second = _case(db_session, owner, "ERASE-SHARED-B")
    stored_filename = "b" * 64 + ".txt"
    target = root / stored_filename
    target.write_bytes(b"shared deidentified fixture")
    _file(db_session, first, target, stored_filename)
    _file(db_session, second, target, stored_filename)

    first_response = client.delete(f"/api/v1/cases/{first.id}", headers=get_auth_headers(owner))
    assert first_response.status_code == 204
    assert target.exists()

    second_response = client.delete(f"/api/v1/cases/{second.id}", headers=get_auth_headers(owner))
    assert second_response.status_code == 204
    assert not target.exists()


def test_case_erasure_treats_an_already_missing_object_as_idempotent(
    client, db_session, test_users, monkeypatch, tmp_path
):
    root = _use_upload_root(monkeypatch, tmp_path)
    owner = test_users["clinician_a"]
    case = _case(db_session, owner, "ERASE-MISSING")
    stored_filename = "c" * 64 + ".txt"
    _file(db_session, case, root / stored_filename, stored_filename)

    response = client.delete(f"/api/v1/cases/{case.id}", headers=get_auth_headers(owner))

    assert response.status_code == 204
    event = db_session.query(AuditEvent).filter(AuditEvent.action == "CASE_DELETED").order_by(AuditEvent.id.desc()).first()
    assert event.details["stored_objects_missing"] == 1
    assert event.details["stored_objects_deleted"] == 0


def test_case_erasure_refuses_a_recorded_path_outside_the_managed_root(
    client, db_session, test_users, monkeypatch, tmp_path
):
    _use_upload_root(monkeypatch, tmp_path)
    owner = test_users["clinician_a"]
    case = _case(db_session, owner, "ERASE-OUTSIDE")
    stored_filename = "d" * 64 + ".txt"
    outside = tmp_path / stored_filename
    outside.write_bytes(b"must remain")
    _file(db_session, case, outside, stored_filename)

    response = client.delete(f"/api/v1/cases/{case.id}", headers=get_auth_headers(owner))

    assert response.status_code == 409
    assert outside.exists()
    assert db_session.query(Case).filter(Case.id == case.id).first() is not None


def test_case_erasure_is_not_delegated_to_case_editors(
    client, db_session, test_users, monkeypatch, tmp_path
):
    root = _use_upload_root(monkeypatch, tmp_path)
    owner = test_users["clinician_a"]
    editor = test_users["clinician_b"]
    case = _case(db_session, owner, "ERASE-OWNER-ONLY")
    stored_filename = "e" * 64 + ".txt"
    target = root / stored_filename
    target.write_bytes(b"must remain")
    _file(db_session, case, target, stored_filename)
    db_session.add(CaseMembership(case_id=case.id, user_id=editor.id, role="EDITOR", granted_by_id=owner.id))
    db_session.commit()

    response = client.delete(f"/api/v1/cases/{case.id}", headers=get_auth_headers(editor))

    assert response.status_code == 403
    assert target.exists()
    assert db_session.query(Case).filter(Case.id == case.id).first() is not None
