"""Read-only orchestration inventory over the existing evidence pipeline."""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.entities import Case, EvidenceStatus, ForecastRecord, InferenceRun, QueuedJob, UploadedFile
from app.services.anatomy_evidence import _latest_reviews
from app.services.evidence_synthesis import eligible_upload, synthesize

VERSION = "case-workflow-v1"
SUCCESS = {EvidenceStatus.COMPLETED, EvidenceStatus.PENDING_HUMAN_REVIEW}


def active_sources(case_id: int, db: Session) -> list[UploadedFile]:
    return [u for u in db.query(UploadedFile).filter(UploadedFile.case_id == case_id).order_by(UploadedFile.id)
            if eligible_upload(u, case_id)]


def pending_reports(case_id: int, db: Session) -> list[UploadedFile]:
    reports = {u.id: u for u in active_sources(case_id, db) if u.modality.value == "REPORT"}
    completed_hashes = {reports[r.file_id].file_hash for r in db.query(InferenceRun).filter(InferenceRun.case_id == case_id)
                        if r.file_id in reports and r.status in SUCCESS and not r.error_message}
    pending = {}
    for upload in reports.values():
        if upload.file_hash not in completed_hashes:
            pending.setdefault(upload.file_hash, upload)
    return list(pending.values())


def snapshot(case: Case, db: Session) -> dict:
    uploads = active_sources(case.id, db)
    ids = {u.id for u in uploads}
    reports = [u.id for u in uploads if u.modality.value == "REPORT"]
    scans = [u.id for u in uploads if u.modality.value != "REPORT"]
    runs = [r for r in db.query(InferenceRun).filter(InferenceRun.case_id == case.id).order_by(InferenceRun.id) if r.file_id in ids]
    latest = {r.file_id: r for r in runs}
    pending = pending_reports(case.id, db)
    queued = db.query(QueuedJob).filter(QueuedJob.case_id == case.id, QueuedJob.status.in_(["QUEUED", "RUNNING"])).all()
    busy_reports = [j.file_id for j in queued if j.file_id in reports and j.kind == "UPLOAD_ANALYSIS"]
    synthesis = synthesize(case.id, db)
    unlinked = [u.id for u in uploads if not u.examination_id]
    regions = sorted({r["atlas_structure_id"] for r in synthesis["report_findings"] if r["assertion"] == "AFFIRMED" and r["atlas_structure_id"]})
    model_outputs = synthesis["model_findings"]
    refused = [a for a in synthesis["abstentions"] if a["upload_id"] in scans]
    superseded = set(synthesis.get("superseded_report_run_ids") or [])  # earlier analyses of re-analysed reports
    findings = [f for r in runs if r.id not in superseded for f in r.findings if not f.failure_reason]
    reviews = _latest_reviews(db, {f.id for f in findings})
    pending_reviews = [f.id for f in findings if not reviews.get(f.id) or reviews[f.id].review_status not in {"CONFIRMED", "REJECTED"}]
    exams = sorted(case.examinations, key=lambda e: e.exam_date)
    linked_exam_ids = {u.examination_id for u in uploads if u.examination_id}
    history = db.query(ForecastRecord).filter(ForecastRecord.case_id == case.id).order_by(ForecastRecord.id.desc()).limit(100).all()
    estimates = [r.id for r in history if r.predicted_value is not None]
    stages = []

    def stage(key, title, status, detail, path, source_ids):
        stages.append({"id": key, "title": title, "status": status, "detail": detail, "path": path, "source_upload_ids": source_ids})

    stage("upload", "Evidence intake", "AVAILABLE" if uploads else "NO_EVIDENCE",
          f"{len(uploads)} active uploads; {len({u.file_hash for u in uploads})} unique content hashes. Withdrawn and superseded sources are excluded.", "/upload", list(ids))
    stage("documents", "Clinical document intelligence", "PROCESSING" if busy_reports else "NEEDS_PROCESSING" if pending else "AVAILABLE" if reports else "NOT_APPLICABLE",
          f"{len(pending)} unique report sources await extraction; {len(synthesis['report_findings'])} distinct findings retained with raw source statements.", "/documents", reports)
    stage("models", "Imaging and signal models", "AVAILABLE" if model_outputs else "ABSTAIN" if refused else "REVIEW_REQUIRED" if scans else "NOT_APPLICABLE",
          f"{len(model_outputs)} stored model result groups. Input type, checkpoint and applicability checks are required for each selected model; source annotations are not predictions.", "/imaging" if any(u.modality.value == "IMAGE" for u in uploads) else "/multimodal", scans)
    stage("examinations", "Examination identity and dates", "REVIEW_REQUIRED" if unlinked else "AVAILABLE" if linked_exam_ids else "NOT_RUN",
          f"{len(unlinked)} uploads lack an examination link. Confirm source identity and actual study dates; upload time is not a study date.", "/cases", unlinked)
    stage("review", "Human source review", "PENDING_HUMAN_REVIEW" if pending_reviews else "AVAILABLE" if findings else "NOT_RUN",
          f"{len(pending_reviews)} source findings await a decision. Review is recorded separately and does not establish clinical model validation.", "/documents/verify", reports)
    stage("synthesis", "Multimodal evidence synthesis", synthesis["status"], synthesis["summary"], "/multimodal", list(ids))
    stage("anatomy", "Source-linked anatomy", "AVAILABLE" if regions else "NOT_AVAILABLE",
          f"{len(regions)} affirmed reported atlas regions. Schematic reference anatomy does not supply patient lesion boundaries or validated registration.", "/anatomy-studio?system=brain" if any(r.startswith("nervous.") for r in regions) else "/anatomy-studio", list(ids))
    stage("comparison", "Historical comparison", "REVIEW_REQUIRED" if len(linked_exam_ids) >= 2 else "INSUFFICIENT_EVIDENCE",
          f"{len(linked_exam_ids)} examinations have active sources. Select a chronological pair and confirm same-patient identity before comparing evidence.", "/history", list(ids))
    stage("forecast", "Conditional forecasting and history", "RESEARCH_PROTOTYPE" if estimates else "NOT_ELIGIBLE" if history else "NOT_RUN",
          f"{len(history)} recent saved evaluations (up to 100); {len(estimates)} historical research estimates. New forecasts require reviewed dated measurements, compatible contexts and chronological backtests. Saved evaluations are historical snapshots.", "/prognosis-studio?organ=brain" if any(r.startswith("nervous.") for r in regions) else "/prognosis-studio", list(ids))
    stage("report", "Source-linked research report", "AVAILABLE" if uploads else "NO_EVIDENCE",
          "Export the workflow, source evidence, synthesis and retained forecast evaluations together; no overall disease confidence is invented.", "/reports", list(ids))
    return {"version": VERSION, "case_id": case.id, "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "COMBINED" if reports and scans else "DOCUMENT_ONLY" if reports else "SCAN_ONLY" if scans else "EMPTY",
            "evidence_mask": synthesis["evidence_mask"], "model_output_mask": synthesis["model_output_mask"],
            "pending_report_upload_ids": [u.id for u in pending], "active_report_job_ids": [j.id for j in queued if j.file_id in reports and j.kind == "UPLOAD_ANALYSIS"],
            "unlinked_upload_ids": unlinked, "stages": stages,
            "sources": [{"upload_id": u.id, "sha256": u.file_hash, "modality": u.modality.value,
                         "examination_id": u.examination_id, "latest_run_id": latest[u.id].id if u.id in latest else None,
                         "latest_run_status": latest[u.id].status.value if u.id in latest else "NOT_RUN"} for u in uploads],
            "examinations": [{"id": e.id, "date": e.exam_date.isoformat(), "modality": e.modality.value,
                              "upload_ids": [u.id for u in uploads if u.examination_id == e.id]} for e in exams],
            "forecast_evaluation_ids": [r.id for r in history], "clinical_validation": "NOT_ESTABLISHED"}
