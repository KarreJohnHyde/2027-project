"""Exercise the existing durable queue across a real synthetic worker crash.

Uses a newly created temporary SQLite database ONLY. No app server, QA database,
GPU, model, real upload or production queue is accessed. The crash occurs after
claim and before handler execution, so this does not claim exactly-once external
side effects for arbitrary mid-handler crashes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
KIND = "REVIEW_SYNTHETIC_CONTROL"
CRASH_EXIT_CODE = 73
MARKER = ".medtwin-isolated-recovery"


def validate_workspace(workspace: Path, marker: str) -> Path:
    workspace = workspace.resolve(strict=True)
    temporary_root = Path(tempfile.gettempdir()).resolve()
    if workspace.parent != temporary_root or not workspace.name.startswith("medtwin-worker-review-"):
        raise ValueError("Recovery test refuses a non-isolated temporary workspace")
    marker_path = workspace / MARKER
    if not marker_path.is_file() or marker_path.read_text(encoding="ascii") != marker:
        raise ValueError("Recovery test isolation marker is missing or mismatched")
    return workspace


def isolated_environment(workspace: Path, marker: str) -> dict[str, str]:
    workspace = validate_workspace(workspace, marker)
    env = dict(os.environ)
    # Override inherited storage settings before any application module imports.
    env.update(ENVIRONMENT="test", DATABASE_URL=f"sqlite:///{(workspace / 'recovery.db').as_posix()}",
               UPLOAD_DIR=str(workspace / "uploads"), MEDTWIN_DB_ENCRYPTION="off", MEDTWIN_STORAGE_ENCRYPTION="off",
               DEV_SEED_ENABLED="false", MEDTWIN_JOB_EXECUTION="worker", MEDTWIN_JOB_LEASE_SECONDS="1",
               MEDTWIN_DEV_SECRET_FILE=str(workspace / "synthetic-signing.key"),
               SECRET_KEY=secrets.token_hex(32),
               PYTHONPATH=str(ROOT / "backend"), PYTHONUTF8="1")
    for name in ("MEDTWIN_DB_KEY_FILE", "MEDTWIN_DB_KEY", "MEDTWIN_STORAGE_KEY_FILE", "MEDTWIN_STORAGE_KEYS",
                 "MEDTWIN_OPEN_WORKSPACE_ACCOUNT", "MEDTWIN_SHARED_WORKSPACE", "BLOB_READ_WRITE_TOKEN"):
        env.pop(name, None)
    return env


def child(step: str, workspace: Path, marker: str) -> int:
    workspace = validate_workspace(workspace, marker)
    expected = f"sqlite:///{(workspace / 'recovery.db').as_posix()}"
    if os.environ.get("ENVIRONMENT") != "test" or os.environ.get("DATABASE_URL") != expected:
        raise ValueError("Recovery child refuses an unexpected database environment")
    sys.path.insert(0, str(ROOT / "backend"))
    from sqlalchemy import text
    from app.database import Base, SessionLocal, engine
    from app.migrations import run_migrations
    from app.models.entities import QueuedJob
    from app.services import job_queue

    if Path(engine.url.database).resolve() != workspace / "recovery.db":
        raise ValueError("Recovery child engine resolved outside isolated storage")
    Base.metadata.create_all(bind=engine)
    run_migrations(engine)
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE IF NOT EXISTS review_control_results (job_id INTEGER PRIMARY KEY, value TEXT NOT NULL)"))

    @job_queue.handler(KIND)
    def synthetic_control(db, job, context):
        context.progress(50, "Synthetic recovery control; no model inference")
        db.execute(text("INSERT INTO review_control_results(job_id, value) VALUES (:job, :value)"),
                   {"job": job.id, "value": "SYNTHETIC_CONTROL_COMPLETED"})
        db.commit()
        return {"synthetic_control": True, "control_result_job_id": job.id}

    def state(db, job):
        db.refresh(job)
        return {"job_id": job.id, "status": job.status, "attempts": job.attempts,
                "progress": job.progress, "lease_owner": job.lease_owner,
                "lease_expires_at": job.lease_expires_at.isoformat() if job.lease_expires_at else None,
                "result_ref": job.result_ref, "job_rows": db.query(QueuedJob).count(),
                "control_result_rows": db.execute(text("SELECT COUNT(*) FROM review_control_results")).scalar_one()}

    with SessionLocal() as db:
        if step == "seed":
            first, created = job_queue.enqueue(db, KIND, payload={"synthetic": True}, requested_by=None,
                                              idempotency_key="isolated-recovery-control-v1", max_attempts=3)
            duplicate, duplicate_created = job_queue.enqueue(db, KIND, payload={"synthetic": True}, requested_by=None,
                                                            idempotency_key="isolated-recovery-control-v1", max_attempts=3)
            result = {"step": step, "created": created, "duplicate_created": duplicate_created,
                      "idempotent_same_id": first.id == duplicate.id, **state(db, first)}
        elif step == "crash":
            claimed = job_queue.claim(db, "synthetic-crashing-child", kinds=[KIND], lease_seconds=1)
            if claimed is None:
                raise RuntimeError("Crash child did not claim the synthetic control")
            result = {"step": step, "crash_point": "AFTER_COMMITTED_CLAIM_BEFORE_HANDLER", **state(db, claimed)}
            print(json.dumps(result), flush=True)
            os._exit(CRASH_EXIT_CODE)
        elif step == "recover":
            before = db.query(QueuedJob).one()
            prior = state(db, before)
            reaped = job_queue.reap_expired(db)
            after_reap = state(db, before)
            claimed = job_queue.claim(db, "synthetic-recovery-child", kinds=[KIND], lease_seconds=1)
            if claimed is None:
                raise RuntimeError("Recovery child did not reclaim the expired synthetic control")
            claimed_state = state(db, claimed)
            completed = job_queue.run_claimed(db, claimed, "synthetic-recovery-child", lease_seconds=1)
            result = {"step": step, "before": prior, "reaped": reaped, "after_reap": after_reap,
                      "after_claim": claimed_state, **state(db, completed)}
        elif step == "verify":
            terminal = db.query(QueuedJob).one()
            duplicate, duplicate_created = job_queue.enqueue(db, KIND, payload={"synthetic": True}, requested_by=None,
                                                            idempotency_key="isolated-recovery-control-v1", max_attempts=3)
            no_more = job_queue.process_next(db, "synthetic-second-drain", kinds=[KIND])
            result = {"step": step, "duplicate_created": duplicate_created, "idempotent_same_id": duplicate.id == terminal.id,
                      "second_drain_claimed": no_more is not None, **state(db, terminal)}
        else:
            raise ValueError("Unknown child step")
    print(json.dumps(result), flush=True)
    engine.dispose()
    return 0


def exercise(*, timeout_seconds: int = 45) -> dict:
    result = {"schema_version": "medtwin-isolated-worker-recovery-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
              "python": sys.version.split()[0], "interpreter": sys.executable,
              "script_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              "queue_source_sha256": hashlib.sha256((ROOT / "backend/app/services/job_queue.py").read_bytes()).hexdigest(),
              "scope": "SYNTHETIC_QUEUE_CRASH_RECOVERY_NOT_MODEL_OR_CLINICAL_ACCURACY", "steps": [],
              "database": "NEW_TEMPORARY_SQLITE_DATABASE_ONLY", "application_or_qa_database_accessed": False,
              "crash_point": "After committed claim, before synthetic handler; not a generic exactly-once side-effect guarantee"}
    revision = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=10)
    result["code_revision"] = revision.stdout.strip() if revision.returncode == 0 else None
    try:
        with tempfile.TemporaryDirectory(prefix="medtwin-worker-review-") as temporary:
            workspace = Path(temporary).resolve()
            marker = secrets.token_hex(24)
            (workspace / MARKER).write_text(marker, encoding="ascii")
            env = isolated_environment(workspace, marker)
            for step in ("seed", "crash", "recover", "verify"):
                if step == "recover":
                    time.sleep(1.2)  # let the actual one-second committed lease expire
                started = time.monotonic()
                process = subprocess.run([sys.executable, str(Path(__file__).resolve()), "--child", step,
                                          "--workspace", str(workspace), "--marker", marker],
                                         env=env, cwd=ROOT, capture_output=True, text=True, timeout=timeout_seconds)
                payloads = [json.loads(line) for line in process.stdout.splitlines() if line.strip().startswith("{")]
                evidence = {"step": step, "exit_code": process.returncode, "seconds": round(time.monotonic() - started, 3),
                            "stdout": process.stdout, "stderr": process.stderr, "snapshot": payloads[-1] if payloads else None}
                result["steps"].append(evidence)
                expected_exit = CRASH_EXIT_CODE if step == "crash" else 0
                if process.returncode != expected_exit or not payloads:
                    raise RuntimeError(f"{step} failed: child exit {process.returncode}, expected {expected_exit}")
            seed, crash, recovered, verified = [step["snapshot"] for step in result["steps"]]
            checks = {
                "enqueue_idempotent": seed["created"] and not seed["duplicate_created"] and seed["idempotent_same_id"],
                "crash_committed_running": crash["status"] == "RUNNING" and crash["attempts"] == 1 and crash["control_result_rows"] == 0,
                "expired_lease_requeued": recovered["reaped"] == 1 and recovered["after_reap"]["status"] == "QUEUED",
                "reclaimed_second_attempt": recovered["after_claim"]["status"] == "RUNNING" and recovered["after_claim"]["attempts"] == 2,
                "completed_once": verified["status"] == "SUCCEEDED" and verified["attempts"] == 2 and verified["progress"] == 100
                                  and verified["job_rows"] == 1 and verified["control_result_rows"] == 1,
                "result_persisted_new_process": verified["result_ref"] == {"synthetic_control": True, "control_result_job_id": seed["job_id"]},
                "terminal_retry_idempotent": not verified["duplicate_created"] and verified["idempotent_same_id"] and not verified["second_drain_claimed"],
                "same_job_throughout": len({state["job_id"] for state in (seed, crash, recovered, verified)}) == 1,
            }
            result["checks"] = checks
            result["status"] = "VERIFIED" if all(checks.values()) else "FAILED"
            result["temporary_database_removed_after_exercise"] = True
    except Exception as exc:
        result.update(status="FAILED", error=f"{type(exc).__name__}: {exc}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review-2026-11-13/worker-recovery.json")
    parser.add_argument("--log", type=Path, default=ROOT / "artifacts/review-2026-11-13/worker-recovery.log")
    parser.add_argument("--child", choices=("seed", "crash", "recover", "verify"), help=argparse.SUPPRESS)
    parser.add_argument("--workspace", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--marker", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.child:
        if args.workspace is None or not args.marker:
            parser.error("Internal child requires an isolation workspace and marker")
        return child(args.child, args.workspace, args.marker)
    result = exercise()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    args.log.parent.mkdir(parents=True, exist_ok=True)
    args.log.write_text("\n".join(f"{step['step']}: exit={step['exit_code']}\n{step['stdout']}\n{step['stderr']}" for step in result["steps"]), encoding="utf-8")
    print(json.dumps({"status": result["status"], "checks": result.get("checks"), "error": result.get("error"), "output": str(args.output)}, indent=2))
    return int(result["status"] != "VERIFIED")


if __name__ == "__main__":
    raise SystemExit(main())
