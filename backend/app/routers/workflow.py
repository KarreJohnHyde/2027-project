"""Case-wide status and explicit report processing through the canonical queue."""
from typing import Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import User
from app.services.auth import get_current_user, verify_case_access
from app.services import case_workflow, job_queue
from app.services.analysis_runner import AnalysisNotPermitted, check_runnable
from app.services.audit_service import log_audit_event

router = APIRouter(tags=["Case workflow"])


class WorkflowStage(BaseModel):
    id: str
    title: str
    status: str
    detail: str
    path: str
    source_upload_ids: list[int]


class WorkflowSnapshot(BaseModel):
    version: str
    case_id: int
    generated_at: str
    mode: Literal["EMPTY", "COMBINED", "DOCUMENT_ONLY", "SCAN_ONLY"]
    evidence_mask: dict[str, int]
    model_output_mask: dict[str, int]
    pending_report_upload_ids: list[int]
    active_report_job_ids: list[int]
    unlinked_upload_ids: list[int]
    stages: list[WorkflowStage]
    sources: list[dict]
    examinations: list[dict]
    forecast_evaluation_ids: list[int]
    clinical_validation: str


class ProcessReportsRequest(BaseModel):
    max_reports: int = Field(default=10, ge=1, le=20)
    model_config = ConfigDict(extra="forbid")


@router.get("/cases/{case_id}/workflow", response_model=WorkflowSnapshot)
def get_workflow(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db, access="read")
    return case_workflow.snapshot(case, db)


@router.post("/cases/{case_id}/workflow/process-reports")
def process_reports(case_id: int, request: ProcessReportsRequest, db: Session = Depends(get_db),
                    current_user: User = Depends(get_current_user)):
    case = verify_case_access(case_id, current_user, db)
    results = []
    for upload in case_workflow.pending_reports(case.id, db)[:request.max_reports]:
        try:
            check_runnable(upload)
        except AnalysisNotPermitted:
            results.append({"upload_id": upload.id, "status": "BLOCKED", "reason": "Active source content is unavailable from storage."})
            continue
        job, created = job_queue.enqueue(db, "UPLOAD_ANALYSIS", payload={"file_id": upload.id},
            requested_by=current_user, case_id=case.id, file_id=upload.id)
        if job_queue.execution_mode() == "inline" and job.status == "QUEUED":
            worker = f"api-inline:{job_queue.default_worker_id()}"
            claimed = job_queue.claim(db, worker, job_id=job.id)
            if claimed is not None:
                job = job_queue.run_claimed(db, claimed, worker)
        results.append({"upload_id": upload.id, "status": job.status, "created": created, "job": job_queue.serialize(job)})
    if results:
        log_audit_event(db=db, action="CASE_WORKFLOW_REPORT_PROCESSING", resource_type="CASE", resource_id=str(case.id), user=current_user,
            details={"case_id": case.id, "uploads": [{"id": r["upload_id"], "status": r["status"]} for r in results]})
    return {"version": case_workflow.VERSION, "case_id": case.id, "results": results,
            "notice": "Report extraction only. Select imaging models using their explicit input contracts; clinical review and examination identity are not confirmed automatically.",
            "workflow": case_workflow.snapshot(case, db)}
