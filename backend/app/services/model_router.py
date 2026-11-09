"""Task-scoped upload routing. Selection never bypasses an adapter's content gates."""
from __future__ import annotations

from pathlib import Path
import re

from app.models.entities import ModalityType
from app.services import model_inference, upload_store
from app.services.imaging_readers import read_metadata, ImagingReadError

VERSION = "capability-router-v1"
TASKS = {
    "classification": {"image_classification", "multilabel_image_classification", "multilabel_ecg_classification"},
    "detection": {"object_detection"},
    "segmentation": {"semantic_segmentation", "volumetric_semantic_segmentation"},
    "ef_regression": {"echo_ef_regression"},
}


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower().replace("tumor", "tumour").replace("hemorrhage", "haemorrhage")).strip()


def infer_input(upload):
    """Only digital container/metadata evidence; never infer disease from a filename."""
    if upload.modality == ModalityType.ECG:
        return "ECG", "uploaded_signal_contract"
    if Path(upload.stored_filename).suffix.lower() == ".dcm":
        with upload_store.materialize(Path(upload.file_path)) as plain:
            metadata = read_metadata(plain)
        tag = metadata.get("modality_tag")
        body = normalized(metadata.get("body_part") or "")
        if tag == "CT" and body in {"head", "brain"}:
            return "HEAD_CT", "DICOM_modality_and_body_part_need_source_confirmation"
        # A generic CT tag cannot establish that a scan is a kidney-stone slice.
        # Other anatomy and sequence contracts require an explicit source declaration.
    return None, "source_declaration_required"


def plan_upload(upload, *, declared_input_type=None, task="auto", target=None, anatomy=None, options=None, db=None):
    base = {"router_version": VERSION, "upload_id": upload.id, "selected_model_id": None, "handler": None,
            "candidates": [], "rejected": [], "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED",
            "content_gates": "Still required at execution; routing is not an applicability or diagnostic result."}
    if not upload.is_associated or upload.withdrawn_at is not None or upload.superseded_by_file_id is not None:
        return {**base, "status": "ABSTAIN", "reason": "UPLOAD_NOT_ACTIVE_EVIDENCE"}
    if not upload_store.available(Path(upload.file_path)):
        return {**base, "status": "ABSTAIN", "reason": "STORED_FILE_MISSING"}
    if task == "forecast":
        return {**base, "status": "ABSTAIN", "reason": "NO_VALIDATED_UPLOAD_FORECAST_MODEL",
                "requirements": ["defined outcome and horizon", "source-linked longitudinal observations", "chronological external validation", "applicable validated forecast model"]}
    if upload.modality == ModalityType.REPORT:
        if task not in ("auto", "document_extraction"):
            return {**base, "status": "ABSTAIN", "reason": "CSV_OR_REPORT_IS_NOT_A_GENERIC_DISEASE_MODEL_INPUT"}
        return {**base, "status": "SELECTED", "selected_model_id": "clinical_rules_v1", "handler": "report_analysis",
                "reason": "SOURCE_LINKED_REPORT_EXTRACTION_ONLY", "diagnostic_predictions": False}
    try:
        declaration, evidence = (declared_input_type, "explicit_source_declaration") if declared_input_type else infer_input(upload)
    except (OSError, ValueError, ImagingReadError):
        return {**base, "status": "ABSTAIN", "reason": "INPUT_METADATA_UNREADABLE"}
    base.update(declared_input_type=declaration, declaration_evidence=evidence)
    if not declaration:
        return {**base, "status": "NEEDS_CONTEXT", "reason": "SOURCE_INPUT_TYPE_REQUIRED",
                "required_fields": ["declared_input_type"], "notice": "A standalone raster/volume filename does not establish anatomy or modality."}
    if declaration not in model_inference.MODALITY_LABELS:
        return {**base, "status": "ABSTAIN", "reason": "INPUT_TYPE_NOT_SUPPORTED"}
    for model in model_inference._load_registry()["models"]:
        if not model.get("research_inference") or declaration not in model.get("supported_modalities", []):
            continue
        if task != "auto" and model.get("task") not in TASKS.get(task, set()):
            continue
        if anatomy and normalized(anatomy) != normalized(model.get("anatomy", "")):
            continue
        if target and normalized(target) not in {normalized(c) for c in model.get("supported_classes", [])}:
            continue
        reasons = model_inference.research_gate(model)["blockers"]
        if not reasons:
            try:
                model_inference.check_input(model, upload, declaration, options or {}, db)
            except model_inference.InferenceNotPermitted as exc:
                reasons = [str(exc)]
        if reasons:
            base["rejected"].append({"model_id": model["model_id"], "reasons": reasons})
        else:
            base["candidates"].append({"model_id": model["model_id"], "display_name": model["display_name"],
                                       "task": model["task"], "anatomy": model.get("anatomy"),
                                       "supported_classes": model.get("supported_classes", []),
                                       "checkpoint_sha256": model["artifact_bundle"].get("checkpoint_sha256")})
    if len(base["candidates"]) == 1:
        return {**base, "status": "SELECTED", "selected_model_id": base["candidates"][0]["model_id"], "handler": "registered_research",
                "reason": "UNIQUE_COMPATIBLE_REGISTERED_TASK"}
    if base["candidates"]:
        return {**base, "status": "AMBIGUOUS", "reason": "MULTIPLE_DISTINCT_SUPPORTED_TASKS", "required_fields": ["task or target or anatomy"],
                "notice": "Metrics from different datasets are not used to rank models as interchangeable."}
    return {**base, "status": "ABSTAIN", "reason": "NO_COMPATIBLE_RUNNABLE_MODEL"}
