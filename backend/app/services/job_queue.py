"""Durable job queue backed by the application database.

Why database-backed: the stack has no Redis or broker, and job state must survive
API and worker restarts. Claims are atomic compare-and-set updates, so several
worker processes can share one queue. A running job holds a lease that the worker
extends with heartbeats; if the worker dies, the lease expires and the job is
reclaimed (or failed after max_attempts). GPU jobs respect a concurrency quota.

Execution modes (MEDTWIN_JOB_EXECUTION):
    inline  the API enqueues and immediately runs the job through the same claim
            path (default; keeps request/response behaviour for tests and CLI use)
    worker  the API only enqueues; `python -m app.worker` processes jobs
"""

from __future__ import annotations

import os
import socket
from datetime import datetime, timedelta, timezone
from typing import Callable, Optional

from sqlalchemy import or_, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models.entities import QueuedJob, User

TERMINAL = {"SUCCEEDED", "FAILED", "CANCELLED"}
DEFAULT_LEASE_SECONDS = int(os.getenv("MEDTWIN_JOB_LEASE_SECONDS", "120"))
GPU_SLOTS = int(os.getenv("MEDTWIN_GPU_SLOTS", "1"))

Handler = Callable[[Session, QueuedJob, "JobContext"], dict]
HANDLERS: dict[str, Handler] = {}


def handler(kind: str) -> Callable[[Handler], Handler]:
    def register(function: Handler) -> Handler:
        HANDLERS[kind] = function
        return function
    return register


def execution_mode() -> str:
    mode = os.getenv("MEDTWIN_JOB_EXECUTION", "inline").strip().lower()
    return mode if mode in {"inline", "worker"} else "inline"


def now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def default_worker_id() -> str:
    return f"{socket.gethostname()}:{os.getpid()}"


class JobCancelled(Exception):
    """Raised inside a handler when cancellation was requested."""


class RetryableJobError(Exception):
    """A transient failure; the job is re-queued if attempts remain."""


class JobContext:
    """Passed to handlers: progress reporting, lease heartbeats and cancellation checks."""

    def __init__(self, db: Session, job: QueuedJob, worker_id: str, lease_seconds: int):
        self.db, self.job, self.worker_id, self.lease_seconds = db, job, worker_id, lease_seconds

    def progress(self, percent: int, message: Optional[str] = None) -> None:
        self.db.refresh(self.job)
        if self.job.cancel_requested:
            raise JobCancelled()
        self.db.execute(
            update(QueuedJob).where(QueuedJob.id == self.job.id, QueuedJob.lease_owner == self.worker_id)
            .values(progress=max(0, min(100, percent)), message=(message or self.job.message or "")[:256],
                    lease_expires_at=now() + timedelta(seconds=self.lease_seconds))
        )
        self.db.commit()


def serialize(job: QueuedJob) -> dict:
    return {
        "id": job.id, "kind": job.kind, "status": job.status, "resource": job.resource, "case_id": job.case_id,
        "file_id": job.file_id, "attempts": job.attempts, "max_attempts": job.max_attempts, "progress": job.progress,
        "message": job.message, "last_error": job.last_error, "result_ref": job.result_ref, "cancel_requested": job.cancel_requested,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "started_at": job.started_at.isoformat() if job.started_at else None,
        "finished_at": job.finished_at.isoformat() if job.finished_at else None,
        "execution_mode": execution_mode(),
    }


def enqueue(db: Session, kind: str, *, payload: dict, requested_by: Optional[User], case_id: Optional[int] = None,
            file_id: Optional[int] = None, resource: str = "CPU", idempotency_key: Optional[str] = None,
            max_attempts: int = 3, reuse_active: bool = True) -> tuple[QueuedJob, bool]:
    """Returns (job, created). An existing job is returned for a repeated idempotency key,
    or (with reuse_active) while an identical job for the same file is still queued or running."""
    if kind not in HANDLERS:
        raise ValueError(f"No handler registered for job kind {kind!r}.")
    if idempotency_key:
        existing = db.query(QueuedJob).filter(QueuedJob.idempotency_key == idempotency_key).first()
        if existing:
            return existing, False
    if reuse_active and file_id is not None:
        active = db.query(QueuedJob).filter(QueuedJob.kind == kind, QueuedJob.file_id == file_id,
                                            QueuedJob.status.in_(["QUEUED", "RUNNING"])).order_by(QueuedJob.id).first()
        if active and active.payload == payload:
            return active, False
    job = QueuedJob(kind=kind, status="QUEUED", resource=resource, case_id=case_id, file_id=file_id, payload=payload,
                    idempotency_key=idempotency_key, requested_by_id=requested_by.id if requested_by else None, max_attempts=max_attempts)
    db.add(job)
    try:
        db.commit()
    except IntegrityError:  # a concurrent request inserted the same idempotency key
        db.rollback()
        return db.query(QueuedJob).filter(QueuedJob.idempotency_key == idempotency_key).one(), False
    db.refresh(job)
    return job, True


def reap_expired(db: Session) -> int:
    """Returns jobs whose worker stopped heartbeating to the queue, or fails them after max_attempts."""
    expired = db.query(QueuedJob).filter(QueuedJob.status == "RUNNING", QueuedJob.lease_expires_at < now()).all()
    for job in expired:
        if job.attempts >= job.max_attempts:
            job.status, job.finished_at = "FAILED", now()
            job.last_error = f"LEASE_EXPIRED: worker {job.lease_owner} stopped responding; attempts exhausted."
        else:
            job.status = "QUEUED"
            job.message = f"Re-queued after worker {job.lease_owner} stopped responding."
        job.lease_owner, job.lease_expires_at = None, None
    if expired:
        db.commit()
    return len(expired)


def claim(db: Session, worker_id: str, *, job_id: Optional[int] = None, kinds: Optional[list[str]] = None,
          lease_seconds: int = DEFAULT_LEASE_SECONDS) -> Optional[QueuedJob]:
    reap_expired(db)
    query = db.query(QueuedJob.id, QueuedJob.resource).filter(
        QueuedJob.status == "QUEUED", or_(QueuedJob.not_before.is_(None), QueuedJob.not_before <= now()))
    if job_id is not None:
        query = query.filter(QueuedJob.id == job_id)
    if kinds:
        query = query.filter(QueuedJob.kind.in_(kinds))
    gpu_running = db.query(QueuedJob).filter(QueuedJob.status == "RUNNING", QueuedJob.resource == "GPU").count()
    for candidate_id, resource in query.order_by(QueuedJob.id).limit(20).all():
        if resource == "GPU" and gpu_running >= GPU_SLOTS:
            continue
        claimed = db.execute(
            update(QueuedJob).where(QueuedJob.id == candidate_id, QueuedJob.status == "QUEUED")
            .values(status="RUNNING", lease_owner=worker_id, lease_expires_at=now() + timedelta(seconds=lease_seconds),
                    attempts=QueuedJob.attempts + 1, started_at=now(), progress=0)
        )
        db.commit()
        if claimed.rowcount == 1:
            return db.get(QueuedJob, candidate_id)
    return None


def _finish(db: Session, job: QueuedJob, worker_id: str, **values) -> None:
    db.execute(update(QueuedJob).where(QueuedJob.id == job.id, QueuedJob.lease_owner == worker_id)
               .values(lease_owner=None, lease_expires_at=None, finished_at=now(), **values))
    db.commit()
    db.refresh(job)


def run_claimed(db: Session, job: QueuedJob, worker_id: str, lease_seconds: int = DEFAULT_LEASE_SECONDS) -> QueuedJob:
    """Runs a job this worker has claimed and records the outcome."""
    context = JobContext(db, job, worker_id, lease_seconds)
    try:
        result_ref = HANDLERS[job.kind](db, job, context)
    except JobCancelled:
        _finish(db, job, worker_id, status="CANCELLED", message="Cancelled while running.")
    except RetryableJobError as exc:
        db.rollback()
        if job.attempts < job.max_attempts:
            db.execute(update(QueuedJob).where(QueuedJob.id == job.id).values(
                status="QUEUED", lease_owner=None, lease_expires_at=None, last_error=str(exc)[:2000],
                not_before=now() + timedelta(seconds=min(300, 5 * 2 ** job.attempts))))
            db.commit()
            db.refresh(job)
        else:
            _finish(db, job, worker_id, status="FAILED", last_error=str(exc)[:2000])
    except Exception as exc:  # noqa: BLE001 - every failure must be recorded on the job
        db.rollback()
        _finish(db, job, worker_id, status="FAILED", last_error=f"{type(exc).__name__}: {exc}"[:2000])
    else:
        _finish(db, job, worker_id, status="SUCCEEDED", progress=100, result_ref=result_ref, message="Completed.")
    return job


def process_next(db: Session, worker_id: str, kinds: Optional[list[str]] = None) -> Optional[QueuedJob]:
    job = claim(db, worker_id, kinds=kinds)
    return run_claimed(db, job, worker_id) if job else None


def cancel(db: Session, job: QueuedJob) -> QueuedJob:
    if job.status == "QUEUED":
        job.status, job.finished_at, job.message = "CANCELLED", now(), "Cancelled before it started."
    elif job.status == "RUNNING":
        job.cancel_requested = True
        job.message = "Cancellation requested; the worker stops at its next checkpoint."
    db.commit()
    db.refresh(job)
    return job
