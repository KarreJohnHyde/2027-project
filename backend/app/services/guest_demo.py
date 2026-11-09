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
from app.models.entities import Case, UploadedFile, User, UserRole, VerificationStatus
from app.services import job_queue
from app.services.audit_service import log_audit_event
from app.services.auth import get_password_hash
from app.services.file_storage import save_uploaded_file

GUEST_SESSION_HOURS = 24
GUEST_PREFIX = "guest-"
DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo"
# Upload order is the order a reader would meet them: first laboratory panel, the CT, the follow-up panel.
DEMO_DOCUMENTS = ("demo_lab_report_march.txt", "demo_ct_abdomen_report.txt", "demo_lab_report_june.txt")


def _analyse(db: Session, user: User, record: UploadedFile) -> str:
    """Queue the same analysis a normal upload gets; run it now when jobs execute inline."""
    job, _ = job_queue.enqueue(db, "UPLOAD_ANALYSIS", payload={"file_id": record.id}, requested_by=user,
                               case_id=record.case_id, file_id=record.id)
    if job_queue.execution_mode() != "worker" and job.status == "QUEUED":
        claimed = job_queue.claim(db, f"guest-demo:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is not None:
            job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    return job.status


async def create_guest_demo(db: Session) -> tuple[User, Case, dict[str, str]]:
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
        # The analysis blocks (OCR-free here, but rules, WSL tools and the database); off the event loop, other
        # requests keep being served. The session is used by one thread at a time.
        analyses[name] = await run_in_threadpool(_analyse, db, user, record)
    return user, case, analyses
