"""Task-scoped upload routing. Selection never bypasses an adapter's content gates."""
from __future__ import annotations

from pathlib import Path
import re

from app.models.entities import ModalityType
from app.services import model_inference, upload_store
from app.services.imaging_readers import BODY_PART_SYSTEMS, read_metadata, ImagingReadError
from app.services.dicom_raster import DICOM_MODALITIES

VERSION = "capability-router-v2"
TASKS = {
    "classification": {"image_classification", "multilabel_image_classification", "multilabel_ecg_classification"},
    "detection": {"object_detection"},
    "segmentation": {"semantic_segmentation", "volumetric_semantic_segmentation"},
    "ef_regression": {"echo_ef_regression"},
}
# These are contradiction checks on explicit technical tags, not classifiers of image content.
# Unknown/missing body-part tags still need the source declaration and all adapter/OOD gates.
_DICOM_BODY_PARTS = {
    "MRI": {"HEART", "CHEST", "THORAX"},
    "ANGIOGRAPHY": {"HEART", "CHEST", "THORAX"},
    "HEAD_CT": {"HEAD", "BRAIN", "SKULL"},
    "HEAD_CT_SERIES": {"HEAD", "BRAIN", "SKULL"},
    "BRAIN_MRI_DIFFUSION": {"HEAD", "BRAIN", "SKULL"},
    "BRAIN_MRI_MULTISEQUENCE": {"HEAD", "BRAIN", "SKULL"},
    "CHEST_XRAY": {"CHEST", "THORAX", "LUNG"},
    "CT_CHEST_VOLUME": {"CHEST", "THORAX", "LUNG", "CHESTABDOMEN"},
    "CT_ABDOMEN_VOLUME": {"ABDOMEN", "PELVIS", "LIVER", "KIDNEY", "PANCREAS", "COLON", "CHESTABDOMEN"},
    "XRAY": {"SHOULDER", "ELBOW", "WRIST", "HAND", "ARM", "EXTREMITY"},
}
_VOLUME_DICOM_MODALITIES = {
    "MRI": {"MR"}, "BRAIN_MRI_DIFFUSION": {"MR"}, "BRAIN_MRI_MULTISEQUENCE": {"MR"},
    "CT_ABDOMEN_VOLUME": {"CT"}, "CT_CHEST_VOLUME": {"CT"}, "HEAD_CT_SERIES": {"CT"},
}


def normalized(value):
    return re.sub(r"[^a-z0-9]+", " ", str(value).lower().replace("tumor", "tumour").replace("hemorrhage", "haemorrhage")).strip()


def _source_metadata(upload):
    if Path(upload.stored_filename).suffix.lower() == ".dcm":
        with upload_store.materialize(Path(upload.file_path)) as plain:
            return read_metadata(plain)
    return None


def metadata_conflicts(declaration, metadata):
    """Return a typed contradiction without exposing DICOM descriptive/identifying fields."""
    if metadata is None:
        return None
    tag = str(metadata.get("modality_tag") or "").strip().upper()
    allowed = DICOM_MODALITIES.get(declaration) or _VOLUME_DICOM_MODALITIES.get(declaration)
    if tag and allowed is not None and tag not in allowed:
        return "DICOM_MODALITY_CONTRADICTS_DECLARATION"
    body = re.sub(r"[\s_-]+", "", str(metadata.get("body_part") or "").upper())
    supported = _DICOM_BODY_PARTS.get(declaration)
    if supported and body in BODY_PART_SYSTEMS and body not in supported:
        return "DICOM_BODY_PART_CONTRADICTS_DECLARATION"
    return None


def infer_input(upload, metadata=None):
    """Only digital container/metadata evidence; never infer disease from a filename."""
    if upload.modality == ModalityType.ECG:
        return "ECG", "uploaded_signal_contract"
    if Path(upload.stored_filename).suffix.lower() == ".dcm":
        metadata = metadata if metadata is not None else _source_metadata(upload)
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
        metadata = _source_metadata(upload)
        declaration, evidence = (declared_input_type, "explicit_source_declaration") if declared_input_type else infer_input(upload, metadata)
    except (OSError, ValueError, ImagingReadError):
        return {**base, "status": "ABSTAIN", "reason": "INPUT_METADATA_UNREADABLE"}
    base.update(declared_input_type=declaration, declaration_evidence=evidence)
    if not declaration:
        return {**base, "status": "NEEDS_CONTEXT", "reason": "SOURCE_INPUT_TYPE_REQUIRED",
                "required_fields": ["declared_input_type"], "notice": "A standalone raster/volume filename does not establish anatomy or modality."}
    if declaration not in model_inference.MODALITY_LABELS:
        return {**base, "status": "ABSTAIN", "reason": "INPUT_TYPE_NOT_SUPPORTED"}
    if upload.modality == ModalityType.ECG and declaration != "ECG":
        return {**base, "status": "ABSTAIN", "reason": "SIGNAL_INPUT_CONTRADICTS_DECLARATION"}
    contradiction = metadata_conflicts(declaration, metadata)
    if contradiction:
        return {**base, "status": "ABSTAIN", "reason": contradiction}
    if metadata is not None:
        base["metadata_checks"] = {"status": "NO_KNOWN_TAG_CONTRADICTION",
                                   "limitations": "Technical tags do not verify image content, acquisition protocol or sequence; execution gates remain required."}
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
