"""Execution of one upload analysis, shared by the API (inline mode) and the worker.

Preserves provenance, model version, preprocessing version and explicit failure
states (REJECT, ABSTAIN, ERROR). Files are read through upload_store, so
encrypted uploads are decrypted only for the duration of the analysis.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from app.models.entities import (
    ClinicalReportStatement,
    DocumentedAttribute,
    EvidenceStatus,
    Finding,
    InferenceRun,
    MedicalMeasurement,
    ModalityType,
    RepresentationLevel,
    UploadedFile,
    User,
)
from app.services import upload_store
from app.services.audit_service import log_audit_event
from app.services.ecg_processor import ECGQualityError, analyze_ecg_record
from app.services.image_processor import analyze_medical_image
from app.services.nlp_processor import analyze_clinical_report

logger = logging.getLogger(__name__)


class AnalysisNotPermitted(Exception):
    """The upload cannot enter processing (unassociated or missing from the store)."""


class AnalysisFailed(Exception):
    """The adapter failed; the ERROR run was recorded and is referenced here."""

    def __init__(self, error_run_id: int):
        super().__init__(f"Analysis failed; error recorded as run {error_run_id}.")
        self.error_run_id = error_run_id


def check_runnable(file_record: UploadedFile) -> Path:
    if not file_record.is_associated:
        raise AnalysisNotPermitted("File is marked as UNASSOCIATED. Unassociated files cannot enter case-level processing.")
    path = Path(file_record.file_path)
    if not path.exists():
        raise AnalysisNotPermitted("Stored file missing from disk store.")
    return path


def _persist_report_outputs(db: Session, file_record: UploadedFile, finding: Finding, result: dict) -> None:
    for s in result.get("statements", []):
        db.add(ClinicalReportStatement(
            finding_id=finding.id, case_id=file_record.case_id, entity=s["entity"], negation=s["negation"],
            temporality=s["temporality"], source_span=s["source_span"], source_span_start=s.get("source_span_start"),
            source_span_end=s.get("source_span_end"), entity_text=(s.get("entity_text") or "")[:128] or None,
            entity_start=s.get("entity_start"), entity_end=s.get("entity_end"), category=s.get("category"),
            certainty=s.get("certainty"), experiencer=s.get("experiencer"), comparison=s.get("comparison"),
            section=(s.get("section") or "")[:48] or None, anatomical_site=(s.get("anatomical_site") or "")[:128] or None,
            laterality=s.get("laterality"), anatomy_system=s.get("anatomy_system"), atlas_structure_id=s.get("atlas_structure_id"),
            cues=s.get("cues"), extractor_version=s.get("extractor_version") or result.get("model_version"),
        ))
    for m in result.get("measurements", []):
        db.add(MedicalMeasurement(
            case_id=file_record.case_id, examination_id=file_record.examination_id, source_file_id=file_record.id,
            finding_id=finding.id, name=m["name"], display_name=m["display_name"], value=m["value"],
            result_operator=m.get("result_operator", "="), unit=m["unit"],
            raw_value=m["raw_value"], raw_unit=m["raw_unit"], source_span=m["source_span"],
            source_span_start=m["source_span_start"], source_span_end=m["source_span_end"],
            extraction_method=m.get("extraction_method", "TRANSPARENT_RULE_BASELINE"), review_status=EvidenceStatus.PENDING_HUMAN_REVIEW,
            canonical_code=m.get("canonical_code"), code_system=m.get("code_system"), code_mapping_status=m.get("code_mapping_status"),
            reference_low=m.get("reference_low"), reference_high=m.get("reference_high"), reference_text=m.get("reference_text"),
            reference_source=m.get("reference_source"), documented_flag=m.get("documented_flag"), conversion_status=m.get("conversion_status"),
            documented_date=m.get("documented_date"), anatomy_system=m.get("anatomy_system"), association=m.get("association"),
            source_page=m.get("source_page"),
            source_bbox=m.get("source_bbox"), source_bbox_coordinate_space=m.get("source_bbox_coordinate_space"),
            source_image_width=m.get("source_image_width"), source_image_height=m.get("source_image_height"),
            specimen=m.get("specimen", "NOT_DOCUMENTED"), laboratory_method=m.get("laboratory_method", "NOT_DOCUMENTED"),
            laboratory_name=m.get("laboratory_name", "NOT_DOCUMENTED"),
            reference_low_inclusive=m.get("reference_low_inclusive"), reference_high_inclusive=m.get("reference_high_inclusive"),
            reference_options=m.get("reference_options"), reference_selection=m.get("reference_selection"),
            documented_category=(m.get("documented_category") or None) and m["documented_category"][:64],
            extractor_version=m.get("extractor_version") or result.get("model_version"),
        ))
    for a in result.get("attributes", []):
        db.add(DocumentedAttribute(
            case_id=file_record.case_id, source_file_id=file_record.id, finding_id=finding.id, name=a["name"],
            value_text=a["value_text"], value_number=a["value_number"], unit=a["unit"], parse_status=a["parse_status"],
            raw_text=a["raw_text"][:64], source_span=a["source_span"][:256], source_span_start=a["source_span_start"],
            source_span_end=a["source_span_end"],
        ))


def execute_upload_analysis(db: Session, file_record: UploadedFile, actor: Optional[User]) -> InferenceRun:
    """Runs the modality adapter and persists the run, finding and extracted evidence.

    Returns the completed (or REJECT) run. Raises AnalysisFailed after recording an
    ERROR run when the adapter fails, and AnalysisNotPermitted before starting."""
    file_path = check_runnable(file_record)
    start_time = time.perf_counter()
    started_at = datetime.now(timezone.utc)
    run = InferenceRun(
        case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name="Pending",
        model_version="Pending", preprocessing_version="Pending", status=EvidenceStatus.PENDING_HUMAN_REVIEW, started_at=started_at,
    )
    db.add(run)
    db.flush()
    try:
        with upload_store.materialize(file_path) as plain:
            if file_record.modality == ModalityType.IMAGE:
                result = analyze_medical_image(plain, file_record.file_hash)
            elif file_record.modality == ModalityType.ECG:
                result = analyze_ecg_record(plain, file_record.file_hash)
            elif file_record.modality == ModalityType.REPORT:
                result = analyze_clinical_report(plain, file_record.file_hash)
            else:
                raise ValueError(f"Unknown modality: {file_record.modality}")
        exec_ms = round((time.perf_counter() - start_time) * 1000, 2)
        result_status = EvidenceStatus(result.get("evidence_status", EvidenceStatus.PENDING_HUMAN_REVIEW.value))
        # Execution completion and evidence-review state are separate concepts: a
        # finished extractor may still need review, but the job itself is terminal.
        run.model_name = result["model_name"]
        run.model_version = result["model_version"]
        run.preprocessing_version = result["preprocessing_version"]
        run.execution_time_ms = exec_ms
        run.status = EvidenceStatus.COMPLETED if result_status == EvidenceStatus.PENDING_HUMAN_REVIEW else result_status
        run.error_message = result.get("failure_reason")
        run.completed_at = datetime.now(timezone.utc)
        finding = Finding(
            inference_run_id=run.id, case_id=file_record.case_id, modality=file_record.modality, category=result["category"],
            label=result["label"], raw_confidence=result.get("raw_confidence"), calibrated_confidence=result.get("calibrated_confidence"),
            calibration_status=result.get("calibration_status", "UNCALIBRATED"), visual_explanation_path=result.get("visual_explanation_path"),
            explanation_type=result.get("explanation_type"), representation_level=RepresentationLevel(result.get("representation_level", "L1")),
            anatomical_region=result.get("anatomical_region"), mapping_status=result.get("mapping_status", "L1_GENERIC"),
            evidence_provenance=result.get("provenance"), review_status=result_status, failure_reason=result.get("failure_reason"),
            is_demo=result.get("is_demo", True),
        )
        db.add(finding)
        db.flush()
        if file_record.modality == ModalityType.REPORT:
            _persist_report_outputs(db, file_record, finding, result)
        db.commit()
        log_audit_event(db=db, action="ANALYSIS_JOB_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor, details={
            "case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id,
            "modality": file_record.modality.value, "label": finding.label, "exec_time_ms": exec_ms,
        })
        db.refresh(run)
        return run
    except ECGQualityError as quality_error:
        run.model_name = "ECG Input Validator"
        run.model_version = "quality-v1.0.0"
        run.preprocessing_version = "CSVParser+SignalQuality-v1"
        run.status = EvidenceStatus.REJECT
        run.error_message = str(quality_error)
        run.execution_time_ms = round((time.perf_counter() - start_time) * 1000, 2)
        run.completed_at = datetime.now(timezone.utc)
        finding = Finding(
            inference_run_id=run.id, case_id=file_record.case_id, modality=file_record.modality, category="Cardiac Rhythm",
            label="REJECTED: Poor Signal Quality", representation_level=RepresentationLevel.L1_GENERIC,
            mapping_status="ABSTAIN_QUALITY_FAILURE", review_status=EvidenceStatus.REJECT, failure_reason=str(quality_error), is_demo=False,
        )
        db.add(finding)
        db.commit()
        log_audit_event(db=db, action="ANALYSIS_JOB_REJECTED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor, details={
            "case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id,
            "modality": file_record.modality.value, "reason": str(quality_error),
        })
        db.refresh(run)
        return run
    except Exception as exc:
        logger.exception("Analysis adapter failed for upload ID %s", file_record.id)
        db.rollback()
        error_run = InferenceRun(
            case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name="UNAVAILABLE",
            model_version="NONE", preprocessing_version="FAILED_BEFORE_COMPLETION", status=EvidenceStatus.ERROR,
            error_message="Analysis adapter failed before completion.", execution_time_ms=round((time.perf_counter() - start_time) * 1000, 2),
            started_at=started_at, completed_at=datetime.now(timezone.utc),
        )
        db.add(error_run)
        db.commit()
        log_audit_event(db=db, action="ANALYSIS_JOB_FAILED", resource_type="ANALYSIS_JOB", resource_id=str(error_run.id), user=actor, details={
            "case_id": file_record.case_id, "file_id": file_record.id, "modality": file_record.modality.value, "error_type": type(exc).__name__,
        })
        raise AnalysisFailed(error_run.id) from exc
