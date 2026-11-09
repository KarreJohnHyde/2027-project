"""Local synthetic container + encrypted recovery drill. Never touches production state.

This checks a separate local filesystem, not an off-host disaster recovery site.
Secrets are generated per run and are never printed or included in the report.
"""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import urllib.request
import urllib.error

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def command(args, *, check=True):
    result = subprocess.run(args, capture_output=True, text=True)
    if check and result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed: {result.stderr[-1400:]}")
    return result.stdout.strip()


def request(path, data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request("http://127.0.0.1:18017" + path,
                                 data=None if data is None else json.dumps(data).encode(), headers=headers)
    with urllib.request.urlopen(req, timeout=15) as response:
        return response.status, json.load(response), dict(response.headers)


def main():
    identity = secrets.token_hex(5)
    work = ROOT / "artifacts/audits" / ("docker-drill-" + identity)
    work.mkdir(parents=True)
    data = work / "original-data"; data.mkdir()
    environment = work / "runtime.env"
    db_key, upload_key = secrets.token_hex(32), secrets.token_bytes(32)
    import base64
    signing_key = secrets.token_urlsafe(48)
    environment.write_text("\n".join([
        "ENVIRONMENT=production", "DATABASE_URL=sqlite:////data/database.db", "UPLOAD_DIR=/data/uploads",
        "SECRET_KEY=" + signing_key, "MEDTWIN_DB_ENCRYPTION=sqlcipher", "MEDTWIN_DB_KEY=" + db_key,
        "MEDTWIN_STORAGE_ENCRYPTION=required", "MEDTWIN_STORAGE_KEYS=" + base64.b64encode(upload_key).decode(),
        "DEV_SEED_ENABLED=false", "MEDTWIN_USAGE_PROFILE=commercial", "MEDTWIN_RADGRAPH=off",
        'CORS_ORIGINS=["http://127.0.0.1:18018"]',
    ]) + "\n")
    network, backend, frontend = ("medtwin-drill-" + identity + suffix for suffix in ("", "-api", "-web"))
    report = {"started_at": datetime.now(timezone.utc).isoformat(), "scope": "LOCAL_SYNTHETIC_DRILL_NOT_OFF_HOST_OR_CLINICAL_APPROVAL", "checks": {}}
    def save():
        (work / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    def start_api(name, mount):
        return command(["docker", "run", "-d", "--name", name, "--network", network, "--network-alias", "backend",
                        "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true", "--pids-limit=256",
                        "--tmpfs", "/tmp:rw,noexec,nosuid,size=1073741824,mode=1777", "--env-file", str(environment),
                        "--mount", f"type=bind,source={mount},target=/data", "-p", "127.0.0.1:18017:8000", "project-backend:latest"])
    def ready():
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            try:
                return request("/api/v1/system/readiness")[1]
            except (OSError, ValueError):
                time.sleep(2)
        raise RuntimeError("Container readiness timeout")
    try:
        command(["docker", "network", "create", network])
        start_api(backend, data)
        readiness = ready(); assert readiness["ready"], readiness
        report["checks"]["original_readiness"] = readiness
        command(["docker", "run", "-d", "--name", frontend, "--network", network, "--read-only", "--cap-drop=ALL",
                 "--security-opt=no-new-privileges:true", "--pids-limit=128", "--tmpfs", "/tmp:rw,noexec,nosuid,size=67108864,mode=1777",
                 "-p", "127.0.0.1:18018:8080", "project-frontend:latest"])
        deadline = time.monotonic() + 60
        while True:
            try:
                with urllib.request.urlopen("http://127.0.0.1:18018/", timeout=10) as response:
                    assert response.status == 200
                    report["checks"]["frontend_status"] = response.status
                with urllib.request.urlopen("http://127.0.0.1:18018/api/v1/system/readiness", timeout=10) as response:
                    assert response.status == 200 and json.load(response)["ready"]
                    report["checks"]["frontend_api_proxy"] = "PASSED"
                break
            except OSError:
                if time.monotonic() > deadline:
                    raise
                time.sleep(2)
        username = "synthetic_recovery_drill"
        password = secrets.token_urlsafe(32) + "Aa1!"
        status, user, _ = request("/api/v1/auth/register", {
            "username": username,
            "email": "synthetic-drill@example.invalid",
            "password": password,
            "full_name": "Synthetic recovery fixture",
        })
        assert status == 201
        status, session, _ = request("/api/v1/auth/login", {"username": username, "password": password})
        token = session["access_token"]
        status, case, _ = request("/api/v1/cases", {"pseudonymous_id": "SYNTHETIC-RECOVERY-ONLY"}, token)
        assert status == 201
        boundary = "medtwin" + secrets.token_hex(12)
        payload = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"deidentified\"\r\n\r\ntrue\r\n"
                   f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"synthetic.txt\"\r\nContent-Type: text/plain\r\n\r\n"
                   f"Synthetic recovery fixture. No real patient data.\r\n--{boundary}--\r\n").encode()
        upload_request = urllib.request.Request(f"http://127.0.0.1:18017/api/v1/cases/{case['id']}/uploads", data=payload,
            headers={"Content-Type": "multipart/form-data; boundary=" + boundary, "Authorization": "Bearer " + token})
        with urllib.request.urlopen(upload_request, timeout=30) as response:
            assert response.status == 201
            upload = json.load(response)
        status, models, _ = request("/api/v1/research-models", token=token)
        assert all(not m["gate"]["allowed"] for m in models["models"])
        report["checks"]["commercial_unreviewed_models_refused"] = len(models["models"])
        command(["docker", "stop", backend]); command(["docker", "rm", backend])
        # Recover inside the container at the original /data mount, so persisted
        # upload paths retain their meaning across the Linux/Windows boundary.
        backup_key = secrets.token_bytes(32)
        key_id = hashlib.sha256(backup_key).digest()[:8].hex()
        backup_key_file = work / "backup-keys.json"
        backup_key_file.write_text(json.dumps({"active": key_id, "keys": {key_id: base64.b64encode(backup_key).decode()}}))
        def recovery_cli(arguments):
            command(["docker", "run", "--rm", "--network=none", "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
                     "--tmpfs", "/tmp:rw,noexec,nosuid,size=1073741824,mode=1777", "--env-file", str(environment),
                     "-e", "PYTHONPATH=/app", "-e", "MEDTWIN_BACKUP_KEY_FILE=/run/secrets/backup.json",
                     "--mount", f"type=bind,source={data},target=/data",
                     "--mount", f"type=bind,source={work},target=/out",
                     "--mount", f"type=bind,source={backup_key_file},target=/run/secrets/backup.json,readonly",
                     "--mount", f"type=bind,source={ROOT / 'scripts/recovery_bundle.py'},target=/tools/recovery.py,readonly",
                     "project-backend:latest", "python", "/tools/recovery.py", *arguments])
        started = time.monotonic()
        bundle = work / "recovery.bundle"
        recovery_cli(["backup", "--database", "/data/database.db", "--uploads", "/data/uploads", "--bundle", "/out/recovery.bundle", "--writers-stopped"])
        report["checks"]["backup"] = "ENCRYPTED_BUNDLE_CREATED_WITH_DATABASE_UPLOAD_REFERENCES_CHECKED"
        recovered = work / "recovered"
        recovery_cli(["restore", "--bundle", "/out/recovery.bundle", "--destination", "/out/recovered"])
        report["checks"]["restore"] = "AUTHENTICATED_AND_STAGED_WITH_ORIGINAL_MOUNT_PATHS"
        report["checks"]["local_backup_restore_seconds"] = round(time.monotonic() - started, 3)
        start_api(backend, recovered)
        restored_readiness = ready(); assert restored_readiness["ready"]
        _, restored_session, _ = request("/api/v1/auth/login", {"username": username, "password": password})
        _, restored_case, _ = request(f"/api/v1/cases/{case['id']}", token=restored_session["access_token"])
        assert restored_case["pseudonymous_id"] == "SYNTHETIC-RECOVERY-ONLY"
        download_url = f"http://127.0.0.1:18017/api/v1/uploads/{upload['id']}/content"
        with urllib.request.urlopen(urllib.request.Request(download_url, headers={"Authorization": "Bearer " + restored_session["access_token"]}), timeout=15) as response:
            assert response.read() == b"Synthetic recovery fixture. No real patient data."
        report["checks"]["restored_upload_decryption"] = "PASSED"
        report["checks"]["restored_auth_and_case"] = "PASSED"
        for name in (backend, frontend):
            report["checks"][name.endswith("-api") and "api_image" or "web_image"] = command(["docker", "inspect", "--format", "{{.Image}}", name])
        report["status"] = "PASSED_LOCAL_SYNTHETIC_DRILL"
    except Exception as exc:
        report["status"] = "FAILED_REQUIRES_REVIEW"
        report["error"] = f"{type(exc).__name__}: {exc}"
        for name in (backend, frontend):
            logs = subprocess.run(["docker", "logs", name], capture_output=True, text=True)
            (work / (name + ".log")).write_text(logs.stdout + logs.stderr)
        raise
    finally:
        for name in (frontend, backend):
            command(["docker", "rm", "-f", name], check=False)
        command(["docker", "network", "rm", network], check=False)
        environment.unlink(missing_ok=True)
        (work / "backup-keys.json").unlink(missing_ok=True)
        report["secret_files_removed"] = True
        report["ended_at"] = datetime.now(timezone.utc).isoformat(); save()
    print(json.dumps({"status": report["status"], "report": str(work / "report.json")}))


if __name__ == "__main__":
    # The isolated drill deliberately uses fixed loopback ports. Serialize local
    # invocations so two independent builds cannot start overlapping drills.
    lock_path = ROOT / "artifacts/audits/docker-candidate-drill.lock"
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open("a+b") as lock:
        if lock_path.stat().st_size == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        try:
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SystemExit("Another local recovery drill is using the loopback ports; wait for it to finish.")
        main()
