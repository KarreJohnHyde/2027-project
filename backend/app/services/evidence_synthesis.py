"""Versioned rule-based evidence inventory. Never a learned disease prediction.

Retains abstentions, raw source statements and review decisions. Repeated report
assertions are grouped for display, not counted as independent corroboration.
"""
from __future__ import annotations

from collections import defaultdict
import re

from sqlalchemy.orm import Session

from app.models.entities import ClinicalReportStatement, Finding, InferenceRun, UploadedFile
from app.services.anatomy_evidence import _latest_reviews, _review_provenance
from app.services.effective_evidence import STATEMENT_FIELDS, correction_index, effective_record
from app.services.ocr_text import normalise
from app.services.report_runs import current_statements, superseded_report_run_ids

VERSION = "evidence-concordance-v2"


def _site(value: str | None) -> str | None:
    """Bounded OCR/display normalization; original text remains in source records."""
    if not value:
        return None
    value = normalise(value)[0].casefold()
    value = re.sub(r"parietal\s*l?obe", "parietal lobe", value)
    return " ".join(value.split())


def _reported_identity(effective: dict, span: str, atlas: str | None) -> tuple[str, str | None]:
    entity, site = effective["entity"], _site(effective["anatomical_site"])
    # A generic oedema extraction may duplicate the specific cerebral term.
    # Do not merge oedema in other organs or with no brain context.
    if entity in {"Edema", "Cerebral oedema"} and (
        entity == "Cerebral oedema" or (atlas or "").startswith("nervous.")
        or re.search(r"\b(?:parietal|frontal|temporal|occipital)\b", site or "")
    ):
        entity = "Cerebral oedema"
    if entity == "Lesion" and not site:
        # A pituitary negative and a nonspecific focal-lesion negative have
        # different scopes even when the extractor did not assign an atlas id.
        if re.search(r"\bpituitary\b", normalise(span)[0], re.I):
            site = "pituitary"
        else:
            site = "site unspecified: " + " ".join(normalise(span)[0].casefold().split())
    return entity, site


def eligible_upload(upload: UploadedFile | None, case_id: int) -> bool:
    return bool(upload and upload.case_id == case_id and upload.is_associated and
                upload.withdrawn_at is None and upload.superseded_by_file_id is None)


def synthesize(case_id: int, db: Session) -> dict:
    uploads = {u.id: u for u in db.query(UploadedFile).filter(UploadedFile.case_id == case_id).all()
               if eligible_upload(u, case_id)}
    findings = db.query(Finding).filter(Finding.case_id == case_id).order_by(Finding.id).all()
    reviews = _latest_reviews(db, {f.id for f in findings})
    _, corrections = correction_index(db, case_id)
    groups = {}
    secondary = {}
    rejected = []
    # A report analysed again contributes its current analysis only; earlier runs are history, not repeat evidence.
    superseded_runs = sorted(superseded_report_run_ids(db, [case_id]))
    for statement in (db.query(ClinicalReportStatement)
                      .filter(ClinicalReportStatement.case_id == case_id, current_statements(db, [case_id]))
                      .order_by(ClinicalReportStatement.id)):
        finding = statement.finding
        run = finding.inference_run if finding else None
        if not run or run.case_id != case_id or run.file_id not in uploads or finding.failure_reason:
            continue
        if (statement.experiencer or "PATIENT") != "PATIENT":
            continue
        review = reviews.get(finding.id)
        if review and review.review_status == "REJECTED":
            rejected.append(statement.id)
            continue
        original = {field: getattr(statement, field) for field in STATEMENT_FIELDS.values()}
        resolved = effective_record(original, corrections.get(statement.id, []), STATEMENT_FIELDS)
        if resolved["correction_state"] == "REMOVED_IN_EFFECTIVE_VIEW":
            continue
        effective = resolved["effective"]
        upload = uploads[run.file_id]
        # Equivalent assertions within an examination retain ALL source references.
        # Unlinked files are never treated as independent corroborating examinations.
        atlas = statement.atlas_structure_id if effective["anatomical_site"] == original["anatomical_site"] and effective["laterality"] == original["laterality"] else None
        entity, site = _reported_identity(effective, statement.source_span, atlas)
        side = (effective["laterality"] or "").casefold() or None
        scope = ("exam", upload.examination_id) if upload.examination_id else ("source", upload.file_hash)
        key = (scope, entity, effective["negation"], side, site,
               effective["temporality"], effective["certainty"])
        if (statement.category or "").startswith("MODEL_"):
            # A secondary NLP model's reading of the same report sentences: listed, never a separate finding.
            mention = secondary.setdefault(key, {"entity": entity, "assertion": effective["negation"], "laterality": side,
                                                 "anatomical_site": site if not (site or "").startswith("site unspecified:") else None,
                                                 "category": statement.category, "extractor_versions": [], "statement_ids": []})
            mention["statement_ids"].append(statement.id)
            if statement.extractor_version and statement.extractor_version not in mention["extractor_versions"]:
                mention["extractor_versions"].append(statement.extractor_version)
            continue
        source = {"statement_id": statement.id, "finding_id": finding.id, "run_id": run.id,
                  "upload_id": upload.id, "sha256": upload.file_hash, "page": statement.source_page,
                  "source_span": statement.source_span, "normalized_span": normalise(statement.source_span)[0],
                  "start": statement.source_span_start, "end": statement.source_span_end,
                  "review": _review_provenance(review), "review_status": review.review_status if review else "PENDING_HUMAN_REVIEW",
                  "correction_state": resolved["correction_state"], "original": original}
        if key not in groups:
            groups[key] = {"entity": entity, "assertion": effective["negation"],
                           "laterality": side, "anatomical_site": site if not (site or "").startswith("site unspecified:") else None,
                           "temporality": effective["temporality"], "certainty": effective["certainty"],
                           "examination_id": upload.examination_id, "atlas_structure_id": atlas,
                           "evidence_type": "RADIOLOGIST_OR_CLINICIAN_REPORTED", "sources": [],
                           "patient_registered": False, "independent_image_confirmation": "NOT_ESTABLISHED"}
        groups[key]["sources"].append(source)
    reports = list(groups.values())
    for item in reports:
        item["review_status"] = "CONFIRMED" if all(s["review_status"] == "CONFIRMED" for s in item["sources"]) else "PENDING_HUMAN_REVIEW"
        item["anatomical_association"] = (
            "Reported anatomical association — not patient registered" if item["atlas_structure_id"] else
            "Reported region has no atlas mapping" if item["anatomical_site"] else
            "No anatomical site specified in the extracted statement"
        )
    contradictions = []
    by_entity = defaultdict(list)
    for index, item in enumerate(reports):
        scope = ("exam", item["examination_id"]) if item["examination_id"] else ("source", item["sources"][0]["sha256"])
        by_entity[(scope, item["entity"], item["laterality"], item["anatomical_site"], item["temporality"])].append(index)
    for indices in by_entity.values():
        if {reports[i]["assertion"] for i in indices} >= {"AFFIRMED", "NEGATED"}:
            contradictions.append({"type": "REPORT_ASSERTION_CONFLICT", "report_indices": indices, "resolution": "HUMAN_REVIEW_REQUIRED"})
    models = []
    for finding in findings:
        run = finding.inference_run
        if not run or run.case_id != case_id or run.file_id not in uploads or finding.failure_reason:
            continue
        provenance = finding.evidence_provenance or {}
        if provenance.get("source") != "MODEL_INFERENCE":
            continue
        review = reviews.get(finding.id)
        if review and review.review_status == "REJECTED":
            continue
        models.append({"finding_id": finding.id, "run_id": run.id, "upload_id": run.file_id,
                       "sha256": uploads[run.file_id].file_hash, "examination_id": uploads[run.file_id].examination_id,
                       "modality": uploads[run.file_id].modality.value,
                       "model_id": provenance.get("model_id") or run.model_name, "model_version": run.model_version,
                       "preprocessing_version": run.preprocessing_version, "label": finding.label,
                       "validation_status": provenance.get("output_status", "NOT_ESTABLISHED"),
                       "review_status": review.review_status if review else "PENDING_HUMAN_REVIEW",
                       "provenance": provenance})
    grouped_models = {}
    for output in models:
        key = (output["sha256"], output["model_id"], output["model_version"], output["preprocessing_version"], output["label"])
        previous = grouped_models.get(key)
        grouped_models[key] = {**output,
            "run_ids": (previous["run_ids"] if previous else []) + [output["run_id"]],
            "upload_ids": sorted(set((previous["upload_ids"] if previous else []) + [output["upload_id"]])),
            "output_selection": "LATEST_RUN_FOR_IDENTICAL_SOURCE_MODEL_VERSION_AND_LABEL"}
    models = list(grouped_models.values())
    abstentions = []
    for run in db.query(InferenceRun).filter(InferenceRun.case_id == case_id).order_by(InferenceRun.id):
        if run.file_id in uploads and run.error_message:
            abstentions.append({"run_id": run.id, "upload_id": run.file_id, "model_id": run.model_name,
                                "status": run.status.value, "reason": run.error_message})
    # Applicability refusals from queued jobs can happen before an InferenceRun exists.
    from app.models.entities import QueuedJob
    for job in db.query(QueuedJob).filter(QueuedJob.case_id == case_id, QueuedJob.status == "FAILED"):
        if job.file_id in uploads and job.last_error:
            abstentions.append({"job_id": job.id, "upload_id": job.file_id,
                                "model_id": (job.payload or {}).get("model_id"), "status": "ABSTAIN" if job.last_error.startswith("InferenceNotPermitted:") else "ERROR", "reason": job.last_error})
    attempts = {}
    for attempt in abstentions:
        key = (uploads[attempt["upload_id"]].file_hash, attempt["model_id"], attempt["status"], attempt["reason"])
        group = attempts.setdefault(key, {**attempt, "run_ids": [], "job_ids": [], "upload_ids": [], "attempt_count": 0})
        group["attempt_count"] += 1
        for field in ("run", "job", "upload"):
            value = attempt.get(field + "_id")
            if value is not None and value not in group[field + "_ids"]:
                group[field + "_ids"].append(value)
        if attempt.get("run_id"):
            group["run_id"] = attempt["run_id"]
    abstentions = list(attempts.values())
    modalities = {}
    for modality in ("REPORT", "IMAGE", "ECG", "SIGNAL"):
        files = [u for u in uploads.values() if u.modality.value == modality]
        outputs = [m for m in models if uploads[m["upload_id"]].modality.value == modality]
        modalities[modality] = {"available": bool(files), "missing": not files,
                                "upload_ids": [u.id for u in files], "unique_source_count": len({u.file_hash for u in files}),
                                "model_outputs_available": bool(outputs), "quality": "NOT_ASSESSED",
                                "applicability": "MODEL_SPECIFIC", "human_review": "PER_SOURCE",
                                "calibrated_confidence": None}
    return {"version": VERSION, "method": "RULE_BASED_EVIDENCE_CONCORDANCE", "status": "AVAILABLE" if reports or models else "INSUFFICIENT_EVIDENCE",
            "report_findings": reports, "model_findings": models, "abstentions": abstentions,
            "modalities": modalities, "contradictions": contradictions, "excluded_rejected_statement_ids": rejected,
            "superseded_report_run_ids": superseded_runs,
            "secondary_model_mentions": list(secondary.values()),
            "evidence_mask": {key: int(value["available"]) for key, value in modalities.items()},
            "model_output_mask": {key: int(value["model_outputs_available"]) for key, value in modalities.items()},
            "overall_disease_probability": None, "patient_specific_lesion_location": None,
            "concordance": "NOT_INDEPENDENTLY_ESTABLISHED",
            "summary": "Report findings retained; independent image confirmation is unavailable." if reports and not any(uploads[m["upload_id"]].modality.value == "IMAGE" for m in models) else
                       "Available evidence inventoried. Cross-model label and calibration compatibility have not been established.",
            "limitations": ["Repeated statements and repeated file hashes are not independent corroboration.",
                            "Secondary NLP model readings of the same report text are listed separately, not counted as findings.",
                            "Same-case evidence without a confirmed examination link is not paired evidence.",
                            "This rule-based synthesis is not a trained fusion model or a clinical diagnosis."]}
