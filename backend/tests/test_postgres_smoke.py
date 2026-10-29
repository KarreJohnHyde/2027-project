"""The API on PostgreSQL, as with a hosted database on a serverless deploy. Opt-in: set
MEDTWIN_TEST_POSTGRES_URL to an empty, disposable database (e.g. a local postgres container).
Two API processes share the database the way two serverless instances do."""

import json
import os
import secrets
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

POSTGRES_URL = os.getenv("MEDTWIN_TEST_POSTGRES_URL", "").strip()
pytestmark = pytest.mark.skipif(not POSTGRES_URL, reason="MEDTWIN_TEST_POSTGRES_URL is not set")
BACKEND_DIR = Path(__file__).resolve().parents[1]

INSTANCE = textwrap.dedent(
    """
    import json
    import sys
    from fastapi.testclient import TestClient
    from app.main import app

    step, username, password = sys.argv[1], sys.argv[2], sys.argv[3]
    with TestClient(app) as client:
        token = client.post("/api/v1/auth/login", data={"username": username, "password": password}).json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        if step == "write":
            case_id = client.post("/api/v1/cases", json={"pseudonymous_id": "CASE-POSTGRES-SMOKE"}, headers=headers).json()["id"]
            report = b"Synthetic test report. Creatinine 1.1 mg/dL (0.7 - 1.3). No pleural effusion."
            upload = client.post(f"/api/v1/cases/{case_id}/uploads", files={"file": ("pg.txt", report, "text/plain")},
                                 data={"deidentified": "true"}, headers=headers).json()
            job = client.post(f"/api/v1/uploads/{upload['id']}/analysis-jobs", headers=headers)
            assert job.status_code == 201, job.text
        cases = client.get("/api/v1/cases", headers=headers).json()
        case_id = next(case["id"] for case in cases if case["pseudonymous_id"] == "CASE-POSTGRES-SMOKE")
        measurements = client.get(f"/api/v1/cases/{case_id}/measurements", headers=headers).json()
        ready = client.get("/api/v1/system/readiness").json()["checks"]
        print(json.dumps({"measurements": [(m["name"], m["value"]) for m in measurements],
                          "database": ready["database"]["ready"], "migrations": ready["migrations"]["ready"],
                          "dialect": client.app.state.__dict__.get("dialect") or "postgresql"}))
    """
)


def test_two_instances_share_one_postgres_database(tmp_path):
    username, password = f"pg_smoke_{secrets.token_hex(3)}", secrets.token_urlsafe(18)
    env = {
        **os.environ,
        "ENVIRONMENT": "test",
        "DATABASE_URL": POSTGRES_URL,
        "DEV_SEED_ENABLED": "true",
        "DEV_SEED_USERNAME": username,
        "DEV_SEED_PASSWORD": password,
        "DEV_SEED_EMAIL": f"{username}@example.invalid",
        "DEV_SEED_ROLE": "clinician",
        "MEDTWIN_STORAGE_ENCRYPTION": "off",
    }
    results = []
    for number, step in enumerate(("write", "read"), start=1):
        # Each instance has its own upload directory, like a serverless temp directory.
        completed = subprocess.run([sys.executable, "-c", INSTANCE, step, username, password], cwd=BACKEND_DIR,
                                   env={**env, "UPLOAD_DIR": str(tmp_path / f"instance-{number}")},
                                   capture_output=True, text=True, timeout=300)
        assert completed.returncode == 0, completed.stderr[-3000:]
        results.append(json.loads(completed.stdout.strip().splitlines()[-1]))
    for result in results:
        assert result["database"] and result["migrations"]
        assert result["measurements"] == [["creatinine", 1.1]]
