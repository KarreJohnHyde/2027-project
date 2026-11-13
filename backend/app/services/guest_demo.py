"""Guest demonstration accounts: a temporary sign-in with one synthetic sample case.

The sample documents are fictional and say so on their first line. They go through the ordinary
upload and analysis path, so a guest sees what the pipeline extracts from them, never prepared
results. Guest accounts are kept like every other account (nothing is deleted); only their
sign-in is temporary (GUEST_SESSION_HOURS).
"""

from __future__ import annotations

import io
import secrets
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import Headers

from app.config import UPLOAD_DIR
from app.models.entities import Case, QueuedJob, UploadedFile, User, UserRole, VerificationStatus
from app.services import job_queue
from app.services.audit_service import log_audit_event
from app.services.auth import get_password_hash
from app.services.file_storage import save_uploaded_file

GUEST_SESSION_HOURS = 24
GUEST_PREFIX = "guest-"
DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"
# Upload order is the order a reader would meet them: first laboratory panel, the CT, the follow-up panel.
DEMO_DOCUMENTS = ("demo_lab_report_march.txt", "demo_ct_abdomen_report.txt", "demo_lab_report_june.txt")


def _run(db: Session, job_id: int) -> str:
    """Run one queued demo analysis here when jobs execute inline (a worker picks it up otherwise)."""
    job = db.get(QueuedJob, job_id)
    if job_queue.execution_mode() != "worker" and job is not None and job.status == "QUEUED":
        claimed = job_queue.claim(db, f"guest-demo:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is not None:
            job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    return job.status if job is not None else "MISSING"


def run_demo_analyses(bind, job_ids: list[int]) -> None:
    """Analyse the demo documents after the sign-in has been answered, on a session of its own (the request's session
    is closed by then). Each document is one ordinary upload-analysis job; a failure is recorded on that job."""
    db = Session(bind=bind)
    try:
        for job_id in job_ids:
            _run(db, job_id)
    finally:
        db.close()


async def create_guest_demo(db: Session, defer_analysis: bool = False) -> tuple[User, Case, dict[str, str], list[int]]:
    """A new guest account and its synthetic case with the three fictional documents, each queued for the ordinary
    upload analysis. With defer_analysis the analyses are left queued for run_demo_analyses (or a worker), so the
    demo opens at once instead of waiting for every document to be read."""
    suffix = secrets.token_hex(5)
    user = User(
        username=f"{GUEST_PREFIX}{suffix}", email=f"{GUEST_PREFIX}{suffix}@guest.invalid",
        # Nobody learns this password: a guest signs in once, through the token issued here.
        hashed_password=get_password_hash(secrets.token_urlsafe(32)), full_name="Guest (demo)",
        role=UserRole.PUBLIC, verification_status=VerificationStatus.UNVERIFIED, is_active=True, is_guest=True,
    )
    db.add(user)
    db.flush()
    case = Case(pseudonymous_id=f"DEMO-SYNTHETIC-{suffix.upper()}", patient_ref=None, created_by_id=user.id,
                description="Synthetic demonstration case: fictional documents, not a real patient.")
    db.add(case)
    db.commit()
    db.refresh(user)
    db.refresh(case)
    log_audit_event(db=db, action="GUEST_DEMO_STARTED", resource_type="USER", resource_id=str(user.id), user=user,
                    details={"case_id": case.id, "documents": list(DEMO_DOCUMENTS)})

    analyses: dict[str, str] = {}
    job_ids: list[int] = []
    for name in DEMO_DOCUMENTS:
        upload = UploadFile(file=io.BytesIO((DEMO_DIR / name).read_bytes()), filename=name,
                            headers=Headers({"content-type": "text/plain"}))
        original, stored, digest, size, modality = await save_uploaded_file(upload)
        record = UploadedFile(case_id=case.id, filename=original, stored_filename=stored, file_path=str(UPLOAD_DIR / stored),
                              file_hash=digest, file_size_bytes=size, mime_type="text/plain", modality=modality, is_associated=True,
                              association_notes="Synthetic demonstration document (fictional).")
        db.add(record)
        db.commit()
        db.refresh(record)
        job, _ = job_queue.enqueue(db, "UPLOAD_ANALYSIS", payload={"file_id": record.id}, requested_by=user,
                                   case_id=record.case_id, file_id=record.id)
        job_ids.append(job.id)
        if defer_analysis:
            analyses[name] = job.status
        else:
            # The analysis blocks (OCR-free here, but rules, WSL tools and the database); off the event loop, other
            # requests keep being served. The session is used by one thread at a time.
            analyses[name] = await run_in_threadpool(_run, db, job.id)
    return user, case, analyses, job_ids
