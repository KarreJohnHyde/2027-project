"""Job handlers. Importing this module registers them with app.services.job_queue."""

from __future__ import annotations

from sqlalchemy.orm import Session

from app.models.entities import QueuedJob, UploadedFile, User
from app.services.analysis_runner import AnalysisFailed, AnalysisNotPermitted, execute_upload_analysis
from app.services.job_queue import JobContext, handler
from app.services.model_inference import execute_research_inference


@handler("UPLOAD_ANALYSIS")
def upload_analysis(db: Session, job: QueuedJob, context: JobContext) -> dict:
    file_record = db.get(UploadedFile, job.file_id)
    if file_record is None:
        raise AnalysisNotPermitted("The upload no longer exists.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(10, f"Analysing {file_record.modality.value.lower()} upload")
    try:
        run = execute_upload_analysis(db, file_record, actor)
    except AnalysisFailed as exc:
        raise RuntimeError(f"ANALYSIS_ADAPTER_FAILED: error recorded as analysis run {exc.error_run_id}.") from exc
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("RESEARCH_SERIES_INFERENCE")
def research_series_inference(db: Session, job: QueuedJob, context: JobContext) -> dict:
    from app.routers.modalities import load_series

    records = [db.get(UploadedFile, upload_id) for upload_id in job.payload["upload_ids"]]
    if any(record is None or not record.is_associated or record.withdrawn_at is not None for record in records):
        raise AnalysisNotPermitted("A file of the series no longer exists or is no longer bound to the case.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(10, f"Assembling the series for {job.payload['model_id']}")
    report = load_series(records, job.payload.get("series_reference"), load_pixels=True)
    first = next(record for record in records if record.id == report["ordered_upload_ids"][0]) if report.get("ordered_upload_ids") else records[0]
    context.progress(30, f"Running research model {job.payload['model_id']}")
    run = execute_research_inference(db, first, job.payload["model_id"], job.payload["declared_input_type"], actor,
                                     series={"report": report, "records": records})
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("RESEARCH_MODEL_INFERENCE")
def research_model_inference(db: Session, job: QueuedJob, context: JobContext) -> dict:
    file_record = db.get(UploadedFile, job.file_id)
    if file_record is None:
        raise AnalysisNotPermitted("The upload no longer exists.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(10, f"Running research model {job.payload['model_id']}")
    options = {key: job.payload.get(key) for key in ("companion_upload_id", "amplitude_unit")}
    run = execute_research_inference(db, file_record, job.payload["model_id"], job.payload["declared_input_type"], actor, options)
    return {"inference_run_id": run.id, "run_status": run.status.value}
