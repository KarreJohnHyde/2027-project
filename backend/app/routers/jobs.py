"""Persisted analysis-job status and result metadata."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import InferenceRun, User
from app.schemas.entities import AnalysisJobResponse
from app.services.auth import get_current_user, verify_case_access


router = APIRouter(tags=["Analysis Jobs"])


def serialize_analysis_job(job: InferenceRun) -> dict:
    return {
        "id": job.id,
        "case_id": job.case_id,
        "upload_id": job.file_id,
        "status": job.status,
        "modality": job.modality,
        "model_name": job.model_name,
        "model_version": job.model_version,
        "preprocessing_version": job.preprocessing_version,
        "execution_time_ms": job.execution_time_ms,
        "error_message": job.error_message,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "findings": [
            {
                "id": finding.id,
                "modality": finding.modality,
                "category": finding.category,
                "label": finding.label,
                "raw_confidence": finding.raw_confidence,
                "calibrated_confidence": finding.calibrated_confidence,
                "review_status": finding.review_status,
                "failure_reason": finding.failure_reason,
            }
            for finding in job.findings
        ],
    }


@router.get("/analysis-jobs/{job_id}", response_model=AnalysisJobResponse)
def get_job_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    job = db.query(InferenceRun).filter(InferenceRun.id == job_id).first()
    if not job:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Analysis job ID {job_id} not found.",
        )
    verify_case_access(job.case_id, current_user, db, access="read")
    return serialize_analysis_job(job)


@router.get("/cases/{case_id}/analysis-jobs", response_model=List[AnalysisJobResponse])
def list_case_jobs(
    case_id: int,
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    verify_case_access(case_id, current_user, db, access="read")
    jobs = (
        db.query(InferenceRun)
        .filter(InferenceRun.case_id == case_id)
        .order_by(InferenceRun.started_at.desc())
        .limit(limit)
        .all()
    )
    return [serialize_analysis_job(job) for job in jobs]
