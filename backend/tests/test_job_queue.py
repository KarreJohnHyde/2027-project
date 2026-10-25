"""Durable job queue: API modes, leases, cancellation, idempotency, quotas, and restart persistence.

All inputs are synthetic test fixtures."""

import json
import os
import sqlite3
import subprocess
import sys
import textwrap
from datetime import timedelta
from pathlib import Path

import pytest

from app.models.entities import QueuedJob
from app.services import job_queue
from tests.conftest import get_auth_headers

BACKEND = Path(__file__).resolve().parents[1]


@job_queue.handler("TEST_NOOP")
def _noop(db, job, context):
    context.progress(50, "half way")
    return {"echo": job.payload.get("value")}


def _report_upload(client, headers, pseudonym="CASE-QUEUE"):
    case_id = client.post("/api/v1/cases", json={"pseudonymous_id": pseudonym}, headers=headers).json()["id"]
    body = f"Synthetic queue fixture {pseudonym}. Creatinine 1.0 mg/dL.".encode()
    upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": (f"{pseudonym}.txt", body, "text/plain")},
                         data={"deidentified": "true"}, headers=headers).json()
    return case_id, upload["id"]


def test_inline_mode_records_a_durable_job_for_every_analysis(client, test_users, db_session):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id, upload_id = _report_upload(client, headers, "CASE-QUEUE-INLINE")
    response = client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers)
    assert response.status_code == 201, response.text
    job = db_session.query(QueuedJob).filter(QueuedJob.file_id == upload_id).one()
    assert job.status == "SUCCEEDED" and job.attempts == 1 and job.result_ref["inference_run_id"] == response.json()["id"]
    listed = client.get(f"/api/v1/cases/{case_id}/jobs", headers=headers).json()
    assert [item["id"] for item in listed] == [job.id]


def test_worker_mode_queues_reuses_and_completes(client, test_users, db_session, monkeypatch):
    monkeypatch.setenv("MEDTWIN_JOB_EXECUTION", "worker")
    headers = get_auth_headers(test_users["clinician_a"])
    _case_id, upload_id = _report_upload(client, headers, "CASE-QUEUE-WORKER")
    first = client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers)
    second = client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers)
    assert first.status_code == second.status_code == 202
    job_id = first.json()["queued_job"]["id"]
    assert second.json()["queued_job"]["id"] == job_id, "a still-queued job is reused, not duplicated"
    assert client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()["status"] == "QUEUED"
    job = job_queue.process_next(db_session, "test-worker")
    assert job.id == job_id and job.status == "SUCCEEDED"
    run_id = client.get(f"/api/v1/jobs/{job_id}", headers=headers).json()["result_ref"]["inference_run_id"]
    assert client.get(f"/api/v1/analysis-jobs/{run_id}", headers=headers).json()["status"] == "COMPLETED"


def test_idempotency_key_returns_the_original_job(client, test_users, monkeypatch):
    monkeypatch.setenv("MEDTWIN_JOB_EXECUTION", "worker")
    headers = get_auth_headers(test_users["clinician_a"])
    _case_id, upload_id = _report_upload(client, headers, "CASE-QUEUE-IDEMPOTENT")
    keyed = {**headers, "Idempotency-Key": "retry-123"}
    ids = {client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=keyed).json()["queued_job"]["id"] for _ in range(3)}
    assert len(ids) == 1


def test_cancellation_and_terminal_conflict(client, test_users, db_session, monkeypatch):
    monkeypatch.setenv("MEDTWIN_JOB_EXECUTION", "worker")
    headers = get_auth_headers(test_users["clinician_a"])
    _case_id, upload_id = _report_upload(client, headers, "CASE-QUEUE-CANCEL")
    job_id = client.post(f"/api/v1/uploads/{upload_id}/analysis-jobs", headers=headers).json()["queued_job"]["id"]
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers).json()["status"] == "CANCELLED"
    assert job_queue.claim(db_session, "test-worker") is None
    assert client.post(f"/api/v1/jobs/{job_id}/cancel", headers=headers).status_code == 409
    other = get_auth_headers(test_users["clinician_b"])
    assert client.get(f"/api/v1/jobs/{job_id}", headers=other).status_code in {403, 404}


def test_running_job_cancels_at_its_next_checkpoint(db_session, test_users):
    job, _ = job_queue.enqueue(db_session, "TEST_NOOP", payload={"value": 1}, requested_by=test_users["admin"])
    claimed = job_queue.claim(db_session, "w1", job_id=job.id)
    job_queue.cancel(db_session, claimed)
    assert job_queue.run_claimed(db_session, claimed, "w1").status == "CANCELLED"


def test_expired_lease_is_reclaimed_then_failed_after_max_attempts(db_session, test_users):
    job, _ = job_queue.enqueue(db_session, "TEST_NOOP", payload={"value": 7}, requested_by=test_users["admin"], max_attempts=2)
    job_queue.claim(db_session, "crashed-worker", job_id=job.id)
    job.lease_expires_at = job_queue.now() - timedelta(seconds=1)
    db_session.commit()
    reclaimed = job_queue.claim(db_session, "new-worker", job_id=job.id)
    assert reclaimed is not None and reclaimed.attempts == 2 and reclaimed.lease_owner == "new-worker"
    reclaimed.lease_expires_at = job_queue.now() - timedelta(seconds=1)
    db_session.commit()
    assert job_queue.claim(db_session, "third-worker", job_id=job.id) is None
    db_session.refresh(job)
    assert job.status == "FAILED" and job.last_error.startswith("LEASE_EXPIRED")


def test_a_job_is_claimed_once_and_gpu_quota_is_respected(db_session, test_users, monkeypatch):
    monkeypatch.setattr(job_queue, "GPU_SLOTS", 1)
    gpu_a, _ = job_queue.enqueue(db_session, "TEST_NOOP", payload={"value": "a"}, requested_by=test_users["admin"], resource="GPU")
    gpu_b, _ = job_queue.enqueue(db_session, "TEST_NOOP", payload={"value": "b"}, requested_by=test_users["admin"], resource="GPU")
    cpu, _ = job_queue.enqueue(db_session, "TEST_NOOP", payload={"value": "c"}, requested_by=test_users["admin"])
    assert job_queue.claim(db_session, "w1", job_id=gpu_a.id).id == gpu_a.id
    assert job_queue.claim(db_session, "w2", job_id=gpu_a.id) is None
    assert job_queue.claim(db_session, "w2", job_id=gpu_b.id) is None, "only one GPU job may run at a time"
    assert job_queue.claim(db_session, "w2").id == cpu.id
    finished = job_queue.run_claimed(db_session, db_session.get(QueuedJob, gpu_a.id), "w1")
    assert finished.status == "SUCCEEDED" and finished.result_ref == {"echo": "a"}
    assert job_queue.claim(db_session, "w2", job_id=gpu_b.id) is not None


SEED = textwrap.dedent("""
    import sys
    from pathlib import Path
    from app.database import Base, SessionLocal, engine
    from app.models.entities import Case, UploadedFile, User, UserRole, ModalityType
    from app.services.auth import get_password_hash
    from app.services import job_handlers, job_queue

    upload_dir = Path(sys.argv[1]); scenario = sys.argv[2]
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        user = User(username="queue_user", email="queue@test.medtwin", hashed_password=get_password_hash("QueueUser123!"),
                    full_name="Queue Test", role=UserRole.CLINICIAN, is_active=True)
        db.add(user); db.commit()
        case = Case(pseudonymous_id="CASE-RESTART", created_by_id=user.id); db.add(case); db.commit()
        upload_dir.mkdir(parents=True, exist_ok=True)
        stored = upload_dir / "fixture.txt"
        stored.write_text("Synthetic restart fixture. Hemoglobin 13.2 g/dL. No evidence of effusion.", encoding="utf-8")
        record = UploadedFile(case_id=case.id, filename="fixture.txt", stored_filename="fixture.txt", file_path=str(stored),
                              file_hash="0" * 64, file_size_bytes=stored.stat().st_size, mime_type="text/plain", modality=ModalityType.REPORT)
        db.add(record); db.commit()
        job, _ = job_queue.enqueue(db, "UPLOAD_ANALYSIS", payload={"file_id": record.id}, requested_by=user, case_id=case.id, file_id=record.id)
        if scenario == "crashed":
            from datetime import timedelta
            job_queue.claim(db, "crashed-worker", job_id=job.id)
            job.lease_expires_at = job_queue.now() - timedelta(seconds=5)
            db.commit()
        print(job.id)
""")


@pytest.mark.parametrize("scenario", ["queued", "crashed"])
def test_jobs_survive_process_restarts(tmp_path, scenario):
    database = tmp_path / "queue.db"
    env = {**os.environ, "ENVIRONMENT": "test", "DEV_SEED_ENABLED": "false", "DATABASE_URL": f"sqlite:///{database.as_posix()}",
           "UPLOAD_DIR": str(tmp_path / "uploads"), "MEDTWIN_STORAGE_ENCRYPTION": "off", "SECRET_KEY": "test-only-secret-key-at-least-32-characters",
           "PYTHONPATH": str(BACKEND)}
    seed = tmp_path / "seed.py"
    seed.write_text(SEED, encoding="utf-8")
    # Process 1 enqueues (and for "crashed" claims) the job, then exits.
    created = subprocess.run([sys.executable, str(seed), str(tmp_path / "uploads"), scenario], cwd=BACKEND, env=env, capture_output=True, text=True, timeout=120)
    assert created.returncode == 0, created.stderr
    job_id = int(created.stdout.strip().splitlines()[-1])
    with sqlite3.connect(database) as connection:
        status_before = connection.execute("SELECT status FROM queued_jobs WHERE id = ?", (job_id,)).fetchone()[0]
    assert status_before == ("QUEUED" if scenario == "queued" else "RUNNING")
    # Process 2 is a fresh worker that finds the persisted job and completes it.
    worker = subprocess.run([sys.executable, "-m", "app.worker", "--drain", "--worker-id", "fresh-worker"], cwd=BACKEND, env=env,
                            capture_output=True, text=True, timeout=180)
    assert worker.returncode == 0, worker.stderr
    with sqlite3.connect(database) as connection:
        status, attempts, result_ref = connection.execute("SELECT status, attempts, result_ref FROM queued_jobs WHERE id = ?", (job_id,)).fetchone()
        measurements = connection.execute("SELECT name FROM medical_measurements").fetchall()
    assert status == "SUCCEEDED", worker.stderr
    assert attempts == (1 if scenario == "queued" else 2)
    assert json.loads(result_ref)["inference_run_id"] > 0
    assert measurements == [("hemoglobin",)]
