"""Job handlers. Importing this module registers them with app.services.job_queue."""

from __future__ import annotations
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import EvidenceStatus, InferenceRun, QueuedJob, UploadedFile, User
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
    report = load_series(records, job.payload.get("series_reference"), load_pixels=True, phase=job.payload.get("phase"))
    first = next(record for record in records if record.id == report["ordered_upload_ids"][0]) if report.get("ordered_upload_ids") else records[0]
    context.progress(30, f"Running research model {job.payload['model_id']}")
    run = execute_research_inference(db, first, job.payload["model_id"], job.payload["declared_input_type"], actor,
                                     options={"short_axis_attested": bool(job.payload.get("short_axis_attested"))},
                                     series={"report": report, "records": records})
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("CT_ORGAN_SEGMENTATION")
def ct_organ_segmentation(db: Session, job: QueuedJob, context: JobContext) -> dict:
    from app.services import ct_organ_research
    from app.services.model_inference import _inference_lock

    file_record = db.get(UploadedFile, job.file_id)
    if file_record is None:
        raise AnalysisNotPermitted("The upload no longer exists.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(10, "Segmenting CT structures (TotalSegmentator)")
    with _inference_lock:  # the queue's GPU slot spans processes; this lock covers models run in this one
        run = ct_organ_research.execute(db, file_record, actor, fast=bool(job.payload.get("fast", True)))
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("VIDEO_FRAME_ANALYSIS")
def video_frame_analysis(db: Session, job: QueuedJob, context: JobContext) -> dict:
    from app.services import video_frames

    file_record = db.get(UploadedFile, job.file_id)
    if file_record is None:
        raise AnalysisNotPermitted("The upload no longer exists.")
    if not file_record.is_associated or file_record.withdrawn_at is not None or file_record.case_id != job.case_id:
        raise AnalysisNotPermitted("The video was withdrawn or unassociated after the job was queued.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(5, f"Sampling video frames for {job.payload['model_id']}")
    # run_model and check_distribution take the inference lock per frame, so it is not held here.
    run = video_frames.execute(db, file_record, job.payload["model_id"], float(job.payload["interval_s"]), int(job.payload["max_frames"]),
                               actor, progress=context.progress)
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("RESEARCH_MODEL_INFERENCE")
def research_model_inference(db: Session, job: QueuedJob, context: JobContext) -> dict:
    file_record = db.get(UploadedFile, job.file_id)
    if file_record is None:
        raise AnalysisNotPermitted("The upload no longer exists.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    context.progress(10, f"Running research model {job.payload['model_id']}")
    options = {key: job.payload.get(key) for key in ("companion_upload_id", "amplitude_unit", "age_years", "sex", "frame_index")
               if job.payload.get(key) is not None}
    run = execute_research_inference(db, file_record, job.payload["model_id"], job.payload["declared_input_type"], actor, options)
    return {"inference_run_id": run.id, "run_status": run.status.value}


@handler("MULTIMODEL_INFERENCE")
def multimodel_inference(db: Session, job: QueuedJob, context: JobContext) -> dict:
    from app.services import model_inference
    from app.services.evidence_synthesis import eligible_upload

    upload = db.get(UploadedFile, job.file_id)
    if not eligible_upload(upload, job.case_id):
        raise AnalysisNotPermitted("Upload is not active evidence in this case.")
    actor = db.get(User, job.requested_by_id) if job.requested_by_id else None
    results = []
    model_ids = job.payload["model_ids"]
    for index, model_id in enumerate(model_ids):
        context.progress(round(5 + 90 * index / len(model_ids)), f"Evaluating model {index + 1} of {len(model_ids)}")
        previous = db.query(InferenceRun.id).filter(InferenceRun.file_id == upload.id, InferenceRun.model_name == model_id).order_by(InferenceRun.id.desc()).first()
        try:
            run = execute_research_inference(db, upload, model_id, job.payload["declared_input_type"], actor, job.payload.get("options"))
        except model_inference.InferenceNotPermitted as exc:
            run = model_inference.record_abstention(db, upload, model_id, str(exc), actor)
        except Exception as exc:
            # A failed adapter does not discard the other independent model runs.
            # The adapter may already have committed its failure run.
            if not db.is_active:
                db.rollback()
            run = db.query(InferenceRun).filter(InferenceRun.file_id == upload.id,
                InferenceRun.model_name == model_id, InferenceRun.status == EvidenceStatus.ERROR,
                InferenceRun.id > (previous[0] if previous else 0)).order_by(InferenceRun.id.desc()).first()
            if run is None:
                run = InferenceRun(case_id=upload.case_id, file_id=upload.id, modality=upload.modality,
                    model_name=model_id, model_version="NOT_RUN", preprocessing_version="PREFLIGHT_ONLY",
                    status=EvidenceStatus.ERROR, error_message=f"Model execution failed: {type(exc).__name__}",
                    completed_at=datetime.now(timezone.utc))
                db.add(run); db.commit(); db.refresh(run)
                from app.services.audit_service import log_audit_event
                log_audit_event(db=db, action="RESEARCH_INFERENCE_FAILED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": upload.case_id, "file_id": upload.id, "model_id": model_id, "error_type": type(exc).__name__})
        results.append({"model_id": model_id, "run_id": run.id, "status": run.status.value, "reason": run.error_message})
    produced = sum(result["status"] == "COMPLETED" and not result["reason"] for result in results)
    analysis_status = "COMPLETED" if produced == len(results) else "PARTIAL" if produced else "ERROR" if any(r["status"] == "ERROR" for r in results) else "ABSTAIN"
    return {"results": results, "analysis_status": analysis_status,
            "models_with_outputs": produced, "models_attempted": len(results),
            "probability_combination": "NOT_ESTABLISHED", "outputs_are_independent_model_runs": True,
            "statistical_independence_established": False}
