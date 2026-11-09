import json
from app.services.research_job_progress import snapshots
from tests.conftest import get_auth_headers


def test_progress_sanitises_errors_urls_and_local_paths(tmp_path):
    path = tmp_path / "artifacts/downloads/cohort_recovery_status.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"status": "RUNNING", "updated_at": "2026-11-09T12:00:00Z", "current": "SECRET_SOURCE_URL",
        "cohorts": {"cq500": {"status": "RUNNING", "expected": 491, "items": {
            "a": {"status": "VERIFIED_EXISTING", "source": "SECRET_SOURCE_URL"},
            "b": {"status": "FAILED", "error": "SECRET_LOCAL_PATH_AND_KEY"}}}}}))
    result = snapshots(tmp_path)
    assert result["jobs"][0]["completed"] == 1 and result["jobs"][0]["failed"] == 1
    assert "SECRET" not in json.dumps(result)


def test_missing_or_partial_progress_files_do_not_break_readiness(tmp_path):
    assert snapshots(tmp_path)["available"] is False
    path = tmp_path / "artifacts/downloads/cohort_recovery_status.json"
    path.parent.mkdir(parents=True); path.write_text("{partial")
    assert snapshots(tmp_path)["available"] is False


def test_transfer_sizes_use_allowlisted_paths_and_are_never_verified(tmp_path, monkeypatch):
    from app.services import research_job_progress as progress
    partial = tmp_path / "synthetic.part"
    partial.write_bytes(b"synthetic")
    monkeypatch.setattr(progress, "LIVER_PARTIAL", partial)
    path = tmp_path / "artifacts/downloads/cohort_recovery_status.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"cohorts": {"liver": {"status": "RUNNING", "expected": 1, "items": {}}}}))
    result = snapshots(tmp_path)["jobs"][0]
    assert result["transfer"]["received_bytes"] == 9
    assert result["transfer"]["verified"] is False and result["completed"] == 0
    assert "synthetic.part" not in json.dumps(result)


def test_progress_is_not_available_to_anonymous_or_public_accounts(client, test_users, db_session):
    from app.models.entities import User, UserRole
    public = User(username="progress_public", email="progress@example.invalid", hashed_password="unusable-test-only",
                  role=UserRole.PUBLIC, is_active=True)
    db_session.add(public); db_session.commit()
    assert client.get("/api/v1/system/research-jobs").status_code == 401
    assert client.get("/api/v1/system/research-jobs", headers=get_auth_headers(public)).status_code == 403
    assert client.get("/api/v1/system/research-jobs", headers=get_auth_headers(test_users["clinician_a"])).status_code == 200
