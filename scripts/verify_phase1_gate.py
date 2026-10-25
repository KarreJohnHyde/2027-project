"""Exercise the live Phase 1 persistence gate through the public HTTP contract."""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "backend" / "tests" / "fixtures" / "deidentified_phase1_report.txt"
RESULT = ROOT / "backend" / "runtime" / "phase1-gate-result.json"
BASE_URL = os.environ.get("MEDTWIN_BASE_URL", "http://127.0.0.1:8000/api/v1").rstrip("/")
USERNAME = os.environ["MEDTWIN_GATE_USERNAME"]
PASSWORD = os.environ["MEDTWIN_GATE_PASSWORD"]


def authenticate(client: httpx.Client) -> dict:
    response = client.post(
        f"{BASE_URL}/auth/login",
        json={"username": USERNAME, "password": PASSWORD},
    )
    response.raise_for_status()
    token = response.json()
    client.headers["Authorization"] = f"Bearer {token['access_token']}"
    return token


def main() -> None:
    report_bytes = FIXTURE.read_bytes()
    expected_sha256 = hashlib.sha256(report_bytes).hexdigest()

    with httpx.Client(timeout=30) as client:
        authenticate(client)
        cases_response = client.get(f"{BASE_URL}/cases")
        cases_response.raise_for_status()
        cases = cases_response.json()
        if not cases:
            case_response = client.post(
                f"{BASE_URL}/cases",
                json={
                    "pseudonymous_id": "PHASE1-LIVE-GATE",
                    "description": "De-identified live persistence verification case.",
                },
            )
            case_response.raise_for_status()
            case_record = case_response.json()
        else:
            case_record = cases[0]

        upload_response = client.post(
            f"{BASE_URL}/cases/{case_record['id']}/uploads",
            files={"file": (FIXTURE.name, report_bytes, "text/plain")},
            data={"is_associated": "true", "deidentified": "true"},
        )
        upload_response.raise_for_status()
        upload = upload_response.json()
        if upload["file_hash"] != expected_sha256 or len(upload["file_hash"]) != 64:
            raise RuntimeError("The stored digest does not match the fixture's full SHA-256.")

        job_response = client.post(f"{BASE_URL}/uploads/{upload['id']}/analysis-jobs")
        job_response.raise_for_status()
        job = job_response.json()

    # A fresh client and token model an application reload rather than reusing in-memory state.
    with httpx.Client(timeout=30) as reloaded:
        authenticate(reloaded)
        case_id = case_record["id"]
        uploads = reloaded.get(f"{BASE_URL}/cases/{case_id}/uploads").raise_for_status().json()
        jobs = reloaded.get(f"{BASE_URL}/cases/{case_id}/analysis-jobs").raise_for_status().json()
        findings = reloaded.get(f"{BASE_URL}/cases/{case_id}/findings").raise_for_status().json()
        statements = reloaded.get(f"{BASE_URL}/cases/{case_id}/statements").raise_for_status().json()
        events = reloaded.get(f"{BASE_URL}/cases/{case_id}/provenance").raise_for_status().json()

    reloaded_upload = next((item for item in uploads if item["id"] == upload["id"]), None)
    reloaded_job = next((item for item in jobs if item["id"] == job["id"]), None)
    finding_ids = {item["id"] for item in job["findings"]}
    reloaded_findings = [item for item in findings if item["id"] in finding_ids]
    actions = sorted({item["action"] for item in events})

    if reloaded_upload is None or reloaded_upload["file_hash"] != expected_sha256:
        raise RuntimeError("The upload or its digest did not survive the reload.")
    if reloaded_job is None or not reloaded_findings:
        raise RuntimeError("The analysis job or findings did not survive the reload.")
    if not statements:
        raise RuntimeError("The document processor did not persist any source-linked statements.")
    if not {"FILE_UPLOADED", "ANALYSIS_JOB_COMPLETED"}.issubset(actions):
        raise RuntimeError("The expected upload and analysis audit events were not persisted.")

    result = {
        "verified_at": datetime.now(timezone.utc).isoformat(),
        "base_url": BASE_URL,
        "case_id": case_record["id"],
        "case_pseudonymous_id": case_record["pseudonymous_id"],
        "upload_id": upload["id"],
        "filename": upload["filename"],
        "sha256": expected_sha256,
        "analysis_job_id": job["id"],
        "analysis_job_status": job["status"],
        "finding_review_states": sorted({item["review_status"] for item in reloaded_findings}),
        "statement_count_after_reload": len(statements),
        "audit_actions_after_reload": actions,
        "reload_verified": True,
    }
    RESULT.parent.mkdir(parents=True, exist_ok=True)
    RESULT.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
