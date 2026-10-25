"""Durable background jobs: status, listing and cancellation."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import QueuedJob, User
from app.services import job_queue
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(tags=["Background Jobs"])


def _job(job_id: int, db: Session, user: User, access: str) -> QueuedJob:
    job = db.get(QueuedJob, job_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job not found.")
    if job.case_id is not None:
        verify_case_access(job.case_id, user, db, access=access)
    elif job.requested_by_id != user.id and user.role.value != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not permitted to access this job.")
    return job


@router.get("/jobs/{job_id}")
def get_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    return job_queue.serialize(_job(job_id, db, current_user, "read"))


@router.get("/cases/{case_id}/jobs")
def list_case_jobs(case_id: int, limit: int = Query(100, ge=1, le=500), db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    jobs = db.query(QueuedJob).filter(QueuedJob.case_id == case_id).order_by(QueuedJob.id.desc()).limit(limit).all()
    return [job_queue.serialize(job) for job in jobs]


@router.post("/jobs/{job_id}/cancel")
def cancel_job(job_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    job = _job(job_id, db, current_user, "write")
    if job.status in job_queue.TERMINAL:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Job already {job.status}.")
    job = job_queue.cancel(db, job)
    log_audit_event(db=db, action="JOB_CANCEL_REQUESTED", resource_type="JOB", resource_id=str(job.id), user=current_user,
                    details={"case_id": job.case_id, "status": job.status})
    return job_queue.serialize(job)
