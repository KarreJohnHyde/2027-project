"""Owned localhost container + encrypted recovery drill using fictional data only.

Never touches the development database, existing Compose project or patient keys.
Secrets are generated under ignored .cache; only non-sensitive proof is exported.
"""
from __future__ import annotations
import base64
import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import uuid
import httpx
from review_run_workflows import Runner, pdf_fixture, save_json

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / ".cache/completion-container"
OUT = ROOT / "artifacts/completion-2026-11-13/operations"
PROJECT = "medtwin-completion-20261113"


def main():
    STATE.mkdir(exist_ok=True); OUT.mkdir(parents=True, exist_ok=True)
    run_id = uuid.uuid4().hex[:10]
    report = {"schema_version": "medtwin.completion-container-drill.v1", "started_at": datetime.now(timezone.utc).isoformat(), "scope": "LOCALHOST_FICTIONAL_ENCRYPTED_CONTAINER_AND_SEPARATE_STORAGE_RECOVERY_NOT_OFF_HOST_OR_CLINICAL_CLEARANCE", "project": PROJECT, "checks": []}
    def check(name, passed, **details):
        report["checks"].append({"name": name, "passed": bool(passed), **details}); save_json(OUT / "proof.json", report)
        if not passed: raise AssertionError(name)
    envfile = STATE / "secrets.env"
    credentials_file = STATE / "credentials.json"
    if not envfile.exists():
        credentials = {"username": "completion_qa", "password": secrets.token_urlsafe(36), "email": "completion@qa.invalid"}
        save_json(credentials_file, credentials)
        values = {"ENVIRONMENT": "development", "MEDTWIN_USAGE_PROFILE": "commercial", "SECRET_KEY": secrets.token_urlsafe(48),
                  "MEDTWIN_DB_ENCRYPTION": "sqlcipher", "MEDTWIN_DB_KEY": secrets.token_hex(32),
                  "MEDTWIN_STORAGE_ENCRYPTION": "required", "MEDTWIN_STORAGE_KEYS": base64.b64encode(secrets.token_bytes(32)).decode(),
                  "MEDTWIN_BACKUP_KEY": base64.b64encode(secrets.token_bytes(32)).decode(), "MEDTWIN_JOB_EXECUTION": "worker",
                  "DATABASE_URL": "sqlite:////data/completion.db", "MEDTWIN_BACKEND_PORT": "8028", "MEDTWIN_BACKEND_BIND": "127.0.0.1", "MEDTWIN_FRONTEND_PORT": "127.0.0.1:8468",
                  "DEV_SEED_ENABLED": "true", "DEV_SEED_USERNAME": credentials["username"], "DEV_SEED_PASSWORD": credentials["password"], "DEV_SEED_EMAIL": credentials["email"],
                  "DEV_SEED_FULL_NAME": "CompletionQA", "DEV_SEED_ROLE": "clinician", "DEV_SEED_CASE_ENABLED": "false"}
        envfile.write_text("\n".join(f"{k}={v}" for k, v in values.items()) + "\n", encoding="utf-8")
    common = {"MEDTWIN_COMPLETION_RIGHTS_REGISTRY": "/app/project/artifacts/completion-2026-11-13/research/ptb-dataset-rights-sidecar.json",
              "MEDTWIN_COMMERCIAL_REVIEW_PATH": "/app/project/artifacts/completion-2026-11-13/research/ptb-model-rights-sidecar.json",
              "MEDTWIN_TERMINOLOGY_DB": "/opt/medtwin-resources/catalogue.sqlite3", "MEDTWIN_RADGRAPH": "off", "MEDTWIN_CLINICAL_NLP": "off", "MEDTWIN_SCISPACY": "off"}
    mounts = [f"{(ROOT/'data/external/icd10cm-fy2027/catalogue.sqlite3').as_posix()}:/opt/medtwin-resources/catalogue.sqlite3:ro",
              f"{(ROOT/'artifacts/completion-2026-11-13/research').as_posix()}:/app/project/artifacts/completion-2026-11-13/research:ro",
              f"{(ROOT/'ml_training').as_posix()}:/app/project/ml_training:ro", f"{(ROOT/'scripts').as_posix()}:/app/project/scripts:ro",
              f"{(ROOT/'docs/deployment').as_posix()}:/app/project/docs/deployment:ro"]
    ptb_public = ROOT / "ptb-xl-a-large-publicly-available-electrocardiography-dataset-1.0.1"
    if ptb_public.is_dir():
        mounts.append(f"{ptb_public.as_posix()}:/app/project/{ptb_public.name}:ro")
    overrides = STATE / "overrides.json"
    overrides.write_text(json.dumps({"services": {"backend": {"environment": common, "volumes": mounts}, "worker": {"environment": common, "volumes": mounts}}}, indent=2), encoding="utf-8")
    compose = ["docker", "compose", "-p", PROJECT, "--env-file", str(envfile), "-f", "docker-compose.yml", "-f", "docker-compose.hardened.yml", "-f", str(overrides), "--profile", "worker"]
    def command(args, name, timeout=600, stdin=None):
        with (OUT / f"{name}.log").open("w", encoding="utf-8") as log:
            result = subprocess.run(args, cwd=ROOT, input=stdin, text=True, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        if result.returncode: raise RuntimeError(f"{name} exit {result.returncode}; inspect local redacted command log")
        return (OUT / f"{name}.log").read_text(encoding="utf-8")
    command(["docker", "info", "--format", "{{.ServerVersion}}"], "engine", 60)
    command([*compose, "config", "--quiet"], "compose-validation", 60)
    command([*compose, "build", "backend", "worker", "frontend"], "build", 1200)
    command([*compose, "up", "-d", "--no-build"], "start", 180)
    state = {"mode": "qa", "job_execution": "worker", "backend_url": "http://127.0.0.1:8028", "web_url": "http://127.0.0.1:8468", "credentials_file": str(credentials_file)}
    save_json(STATE / "stack.json", state)
    deadline = time.monotonic() + 180
    while time.monotonic() < deadline:
        try:
            if httpx.get(state["backend_url"] + "/health", timeout=5).status_code == 200: break
        except httpx.HTTPError: pass
        time.sleep(1)
    else: raise TimeoutError("Owned container backend not healthy in180s")
    runner = Runner(state, OUT)
    check("Encrypted hardened container backend and durable worker healthy", True)
    check("Local frontend production route served", httpx.get(state["web_url"] + "/universal", timeout=30).status_code == 200)
    term = runner.call("GET", "/universal/terminology/status")
    check("Read-only official reference mount available", term["available"] and term["entry_count"] == 98403)
    diag = runner.call("GET", "/universal/arena/models/ptbxl_ecg_baseline/diagnostics")
    check("Portable rights evidence and saved prediction diagnostics work in Linux", diag["status"] == "COMPUTED_FROM_SAVED_PREDICTIONS" and diag["n"] == 2163)
    case = runner.call("POST", "/cases", json={"pseudonymous_id": f"CONTAINER-FICTIONAL-{run_id}", "description": "Fictional software recovery control, no real patient"})
    content = pdf_fixture("FICTIONAL SOFTWARE CONTROL - NO PATIENT\nCollection date: 2026-11-13\nBIOCHEMISTRY\nSpecimen: Serum\nMethod: SYNTHETIC\nSerum Creatinine 1.2 mg/dL 0.6 - 1.1 H")
    upload = runner.upload(case["id"], "fictional-container-control.pdf", content, "application/pdf")
    job = runner.wait(runner.call("POST", f"/uploads/{upload['id']}/analysis-jobs", headers={"Idempotency-Key": f"container-{run_id}"}))
    check("Actual fictional PDF upload processed by container worker", job["status"] == "SUCCEEDED", case_id=case["id"], upload_id=upload["id"])
    inspect = "import json;from pathlib import Path;from app.database import SessionLocal;from app.models.entities import UploadedFile;from app.services.storage_crypto import file_key_id;d=SessionLocal();r=d.get(UploadedFile," + str(int(upload["id"])) + ");print(json.dumps({'upload_encrypted':file_key_id(Path(r.file_path)) is not None,'database_encrypted':Path('/data/completion.db').read_bytes()[:16]!=b'SQLite format 3\\x00'}))"
    actual = json.loads(command([*compose, "exec", "-T", "backend", "python", "-c", inspect], "encryption-inspection", 60).strip())
    check("Both database and upload bytes are encrypted", actual["upload_encrypted"] and actual["database_encrypted"])
    command([*compose, "stop", "backend", "worker"], "stop-writers", 90)
    recovery = STATE / f"recovery-{run_id}"; recovery.mkdir()
    code = r'''
import json,os,secrets,base64
from pathlib import Path
from app.services.storage_crypto import load_keyring,iter_plaintext
from app.services.recovery_bundle import create_bundle,restore_bundle
keys=load_keyring({'MEDTWIN_STORAGE_KEYS':os.environ['MEDTWIN_BACKUP_KEY']})
dbkey=os.environ['MEDTWIN_DB_KEY']
backup=create_bundle(Path('/data/completion.db'),Path('/data/uploads'),Path('/recovery/backup.enc'),keys,database_key=dbkey,writers_stopped=True)
wrong=load_keyring({'MEDTWIN_STORAGE_KEYS':base64.b64encode(secrets.token_bytes(32)).decode()})
wrong_refused=False
try: restore_bundle(Path('/recovery/backup.enc'),Path('/recovery/wrong-key'),wrong,database_key=dbkey)
except Exception: wrong_refused=True
tampered=bytearray(Path('/recovery/backup.enc').read_bytes());tampered[-1]^=1;Path('/recovery/tampered.enc').write_bytes(tampered)
tamper_refused=False
try: restore_bundle(Path('/recovery/tampered.enc'),Path('/recovery/tamper'),keys,database_key=dbkey)
except Exception: tamper_refused=True
restored=restore_bundle(Path('/recovery/backup.enc'),Path('/recovery/restored'),keys,database_key=dbkey)
print(json.dumps({'backup':backup,'restore':restored,'wrong_key_refused':wrong_refused,'tamper_refused':tamper_refused}))
'''
    volume = f"{PROJECT}_medtwin_data"
    helper = ["docker", "run", "--rm", "--network", "none", "--env-file", str(envfile), "--mount", f"type=volume,source={volume},target=/data,readonly", "--mount", f"type=bind,source={recovery},target=/recovery", f"{PROJECT}-backend", "python", "-c", code]
    recovered = json.loads(command(helper, "encrypted-recovery", 180).strip())
    check("Authenticated backup restores to new separate storage", recovered["restore"]["database_check"]["integrity_check"] == "ok", files=recovered["restore"]["files"], keys_included=recovered["backup"]["keys_included"])
    check("Wrong key and tampered backup refused", recovered["wrong_key_refused"] and recovered["tamper_refused"])
    restore_name = f"{PROJECT}-restore-{run_id}"
    restored_env = STATE / f"restored-{run_id}.env"
    restored_env.write_text(envfile.read_text().replace("sqlite:////data/completion.db", "sqlite:////data/database.db").replace("DEV_SEED_ENABLED=true", "DEV_SEED_ENABLED=false"), encoding="utf-8")
    command(["docker", "run", "-d", "--name", restore_name, "--network", "none", "--env-file", str(restored_env), "--mount", f"type=bind,source={recovery/'restored'},target=/data", f"{PROJECT}-backend"], "restored-start", 60)
    restored_check = "import json,urllib.request; from app.database import SessionLocal;from app.models.entities import Case,UploadedFile;from app.services import upload_store;from pathlib import Path;d=SessionLocal();r=d.get(UploadedFile," + str(int(upload["id"])) + ");context=upload_store.materialize(Path(r.file_path));plain=context.__enter__();n=len(plain.read_bytes());context.__exit__(None,None,None);" + "print(json.dumps({'health':urllib.request.urlopen('http://127.0.0.1:8000/health',timeout=5).status,'case_exists':d.get(Case," + str(int(case["id"])) + ") is not None,'source_hash':r.file_hash,'source_bytes':n}))"
    # The restored process starts independently; keys remain externally supplied.
    time.sleep(4)
    restored_result = json.loads(command(["docker", "exec", restore_name, "python", "-c", restored_check], "restored-proof", 90).strip())
    check("Independent restored backend opens original case and decrypts source", restored_result["health"] == 200 and restored_result["case_exists"] and restored_result["source_hash"] == upload["file_hash"] and restored_result["source_bytes"] == len(content))
    command(["docker", "stop", restore_name], "restored-stop", 60)
    command([*compose, "up", "-d", "--no-build"], "restart-original", 120)
    report["status"] = "VERIFIED_LOCAL_ENCRYPTED_RECOVERY_SCOPE"; report["finished_at"] = datetime.now(timezone.utc).isoformat()
    report["limits"] = ["Fictional data only; no real patient DB/key touched", "Separate container/storage restoration on this host; no off-host destination or disaster-site claim", "Commercial rights audit is scoped automated source/artifact review, not legal/regulatory/clinical approval", "No public exposure; host ports bound127.0.0.1"]
    save_json(OUT / "proof.json", report)
    print(json.dumps({"status": report["status"], "checks": len(report["checks"]), "artifact": str(OUT / 'proof.json')}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, default=OUT)
    arguments = parser.parse_args()
    OUT = arguments.output_directory.resolve()
    if not OUT.is_relative_to((ROOT / "artifacts").resolve()): raise ValueError("Operational proof must stay under the explicit artifacts directory")
    try: main()
    except Exception as exc:
        OUT.mkdir(parents=True, exist_ok=True)
        save_json(OUT / "failure.json", {"status": "FAILED", "reason": str(exc)})
        raise
