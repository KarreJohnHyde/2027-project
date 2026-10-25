"""
Analysis Execution Router for MedTwin.

Every analysis request becomes a durable job (app/services/job_queue.py). In
inline mode (default) the API runs the job immediately through the same claim
path the worker uses and returns the finished analysis run, as before. In worker
mode (MEDTWIN_JOB_EXECUTION=worker) it returns 202 with the queued job, which
`python -m app.worker` processes; clients poll GET /jobs/{id}.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import InferenceRun, UploadedFile, User
from app.routers.jobs import serialize_analysis_job
from app.schemas.entities import AnalysisJobResponse
from app.services import job_handlers  # noqa: F401 - registers the analysis handler
from app.services import job_queue
from app.services.analysis_runner import AnalysisNotPermitted, check_runnable
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(tags=["Modality Analysis"])


@router.post(
    "/uploads/{file_id}/analysis-jobs",
    response_model=AnalysisJobResponse,
    status_code=status.HTTP_201_CREATED,
    responses={202: {"description": "Queued for the background worker (worker execution mode)."}},
)
def trigger_file_analysis(
    file_id: int,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Executes task-specific analysis on an ingested record, preserving provenance and failure states."""
    file_record = db.query(UploadedFile).filter(UploadedFile.id == file_id).first()
    if not file_record:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, current_user, db)
    try:
        check_runnable(file_record)
    except AnalysisNotPermitted as exc:
        missing = "missing" in str(exc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND if missing else status.HTTP_400_BAD_REQUEST, detail=str(exc))

    key = f"analysis:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(
        db, "UPLOAD_ANALYSIS", payload={"file_id": file_record.id}, requested_by=current_user,
        case_id=file_record.case_id, file_id=file_record.id, idempotency_key=key,
    )
    if job_queue.execution_mode() == "worker" and job.status not in job_queue.TERMINAL:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})

    if job.status == "QUEUED":
        claimed = job_queue.claim(db, f"api-inline:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is not None:
            job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    if job.status == "SUCCEEDED" and job.result_ref:
        run = db.get(InferenceRun, job.result_ref["inference_run_id"])
        return serialize_analysis_job(run)
    if job.status == "RUNNING":
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})
    raise HTTPException(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        detail="Analysis failed; the error state was recorded in provenance.",
    )
