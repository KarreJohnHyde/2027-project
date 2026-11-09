"""Integration checks for the shared pipeline and durable local sessions."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import os
from pathlib import Path
import subprocess
import sys

import jwt
import pytest

from app.local_secrets import resolve_signing_key
from app.models.entities import EvidenceStatus, Finding, ForecastRecord, InferenceRun, ModalityType, QueuedJob, UploadedFile
from app.services.evidence_synthesis import synthesize
from tests.conftest import get_auth_headers
from tests.test_heterogeneous_evidence import REPORT, case_and_upload, montage


def test_local_sessions_survive_new_processes(tmp_path):
    env = {**os.environ, "ENVIRONMENT": "development", "SECRET_KEY": "",
           "DATABASE_URL": f"sqlite:///{(tmp_path / 'state.db').as_posix()}",
           "MEDTWIN_DEV_SECRET_FILE": str(tmp_path / "private" / "signing.key")}
    code = "from app.config import SECRET_KEY; import hashlib; print(hashlib.sha256(SECRET_KEY.encode()).hexdigest())"
    digests = [subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
        env=env, check=True, capture_output=True, text=True).stdout.strip() for _ in range(2)]
    assert digests[0] == digests[1]
    key = (tmp_path / "private" / "signing.key").read_text()
    assert hashlib.sha256(key.encode()).hexdigest() == digests[0]
    token = jwt.encode({"sub": "synthetic-local-session"}, key, algorithm="HS256")
    assert jwt.decode(token, resolve_signing_key("", "development", tmp_path / "private" / "signing.key"), algorithms=["HS256"])["sub"] == "synthetic-local-session"
    assert not (tmp_path / "state.db").exists()
    env.pop("MEDTWIN_DEV_SECRET_FILE")
    separate = []
    for filename in ("one.db", "two.db", "one.db"):
        env["DATABASE_URL"] = f"sqlite:///{(tmp_path / filename).as_posix()}"
        separate.append(subprocess.run([sys.executable, "-c", code], cwd=Path(__file__).resolve().parents[1],
            env=env, check=True, capture_output=True, text=True).stdout.strip())
    assert separate[0] == separate[2]
    assert separate[0] != separate[1]  # Different databases never share the implicit local key.


def test_concurrent_local_startup_does_not_rotate_key(tmp_path):
    path = tmp_path / "concurrent.key"
    with ThreadPoolExecutor(max_workers=6) as pool:
        values = list(pool.map(lambda _: resolve_signing_key("", "development", path), range(12)))
    assert len(set(values)) == 1
    assert resolve_signing_key("configured-key-kept", "development", path) == "configured-key-kept"
    assert path.read_text() == values[0]
    with pytest.raises(RuntimeError):
        resolve_signing_key("", "production", tmp_path / "must-not-exist.key")
    assert not (tmp_path / "must-not-exist.key").exists()
    path.write_text("invalid")
    with pytest.raises(RuntimeError):
        resolve_signing_key("", "development", path)
    assert path.read_text() == "invalid"


def test_combined_workflow_uses_existing_processor_and_preserves_boundaries(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case_id = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "CASE-WORKFLOW-COMBINED"}).json()["id"]
    uploads = []
    for filename, content, mime in [("report.txt", REPORT, "text/plain"), ("film.png", montage(), "image/png")]:
        response = client.post(f"/api/v1/cases/{case_id}/uploads", headers=headers, data={"deidentified": "true"}, files={"file": (filename, content, mime)})
        assert response.status_code == 201
        uploads.append(response.json())
    endpoint = f"/api/v1/cases/{case_id}/workflow"
    snapshot = client.get(endpoint, headers=headers).json()
    assert snapshot["version"] == "case-workflow-v1" and snapshot["mode"] == "COMBINED"
    assert snapshot["pending_report_upload_ids"] == [uploads[0]["id"]]
    assert snapshot["examinations"] == []
    assert set(snapshot["unlinked_upload_ids"]) == {u["id"] for u in uploads}
    response = client.post(endpoint + "/process-reports", headers=headers, json={})
    assert response.status_code == 200, response.text
    assert response.json()["results"][0]["status"] == "SUCCEEDED"
    snapshot = response.json()["workflow"]
    assert snapshot["pending_report_upload_ids"] == []
    assert next(s for s in snapshot["stages"] if s["id"] == "synthesis")["status"] == "AVAILABLE"
    assert next(s for s in snapshot["stages"] if s["id"] == "comparison")["status"] == "INSUFFICIENT_EVIDENCE"
    assert not any(snapshot["model_output_mask"].values())
    run_count = db_session.query(InferenceRun).filter(InferenceRun.case_id == case_id).count()
    assert client.post(endpoint + "/process-reports", headers=headers, json={}).json()["results"] == []
    assert db_session.query(InferenceRun).filter(InferenceRun.case_id == case_id).count() == run_count
    assert db_session.query(InferenceRun).filter(InferenceRun.file_id == uploads[1]["id"]).count() == 0
    for _ in range(2):
        assert client.get(endpoint, headers=headers).status_code == 200
    assert db_session.query(ForecastRecord).filter(ForecastRecord.case_id == case_id).count() == 0
    other = get_auth_headers(test_users["clinician_b"])
    assert client.get(endpoint, headers=other).status_code == 403
    assert client.post(endpoint + "/process-reports", headers=other, json={}).status_code == 403
    db_session.get(UploadedFile, uploads[1]["id"]).is_associated = False
    db_session.commit()
    assert client.get(endpoint, headers=headers).json()["mode"] == "DOCUMENT_ONLY"


def test_worker_workflow_reuses_active_job(client, test_users, monkeypatch):
    monkeypatch.setenv("MEDTWIN_JOB_EXECUTION", "worker")
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "CASE-WORKFLOW-QUEUE"}).json()
    client.post(f"/api/v1/cases/{case['id']}/uploads", headers=headers, data={"deidentified": "true"}, files={"file": ("report.txt", REPORT, "text/plain")})
    endpoint = f"/api/v1/cases/{case['id']}/workflow/process-reports"
    first = client.post(endpoint, headers=headers, json={}).json()
    second = client.post(endpoint, headers=headers, json={}).json()
    assert first["results"][0]["status"] == "QUEUED"
    assert second["results"][0]["job"]["id"] == first["results"][0]["job"]["id"]
    assert second["results"][0]["created"] is False
    assert len(second["workflow"]["active_report_job_ids"]) == 1


def test_forecast_reads_do_not_create_evaluations(client, db_session, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "CASE-FORECAST-READ"}).json()
    endpoint = f"/api/v1/cases/{case['id']}"
    for path in ("/forecast", "/forecasts", "/forecast"):
        response = client.get(endpoint + path, headers=headers)
        assert response.status_code == 200, response.text
        assert response.json()["id"] is None
    assert client.get(endpoint + "/forecast-history", headers=headers).json() == []
    result = client.post(endpoint + "/forecast", headers=headers, json={"case_id": case["id"]})
    assert result.status_code == 200 and result.json()["id"] is not None
    assert len(client.get(endpoint + "/forecast-history", headers=headers).json()) == 1
    assert client.get(endpoint + "/forecast?horizon_days=0", headers=headers).status_code == 422
    assert db_session.query(ForecastRecord).filter(ForecastRecord.case_id == case["id"]).count() == 1


def test_comparison_requires_pair_identity_confirmation(client, test_users):
    headers = get_auth_headers(test_users["clinician_a"])
    case = client.post("/api/v1/cases", headers=headers, json={"pseudonymous_id": "CASE-PAIR-IDENTITY"}).json()
    exams = [client.post(f"/api/v1/cases/{case['id']}/examinations", headers=headers,
        json={"exam_date": date, "modality": "REPORT"}).json() for date in ("2024-01-01T00:00:00", "2024-02-01T00:00:00")]
    endpoint = f"/api/v1/cases/{case['id']}/compare"
    pair = {"prior_exam_id": exams[0]["id"], "current_exam_id": exams[1]["id"]}
    assert client.post(endpoint, headers=headers, json=pair).status_code == 400
    assert client.post(endpoint, headers=headers, json={**pair, "same_patient_confirmed": True}).status_code == 200


def test_repeated_model_outputs_keep_latest_and_all_run_references(db_session, test_users, tmp_path):
    case, upload, _ = case_and_upload(db_session, test_users["clinician_a"], tmp_path)
    upload.modality = ModalityType.IMAGE
    runs = []
    for version in ("checkpoint-a", "checkpoint-a", "checkpoint-b"):
        run = InferenceRun(case_id=case.id, file_id=upload.id, modality=ModalityType.IMAGE, model_name="synthetic-model",
            model_version=version, preprocessing_version="test", status=EvidenceStatus.COMPLETED)
        db_session.add(run); db_session.flush()
        db_session.add(Finding(case_id=case.id, inference_run_id=run.id, modality=ModalityType.IMAGE, category="Synthetic",
            label="Synthetic model output", mapping_status="NOT_MAPPABLE", evidence_provenance={"source": "MODEL_INFERENCE", "model_id": "synthetic-model"}))
        runs.append(run)
    db_session.commit()
    result = synthesize(case.id, db_session)
    assert len(result["model_findings"]) == 2
    first = next(r for r in result["model_findings"] if r["model_version"] == "checkpoint-a")
    assert first["run_ids"] == [runs[0].id, runs[1].id]
    assert first["run_id"] == runs[1].id
    assert result["overall_disease_probability"] is None
