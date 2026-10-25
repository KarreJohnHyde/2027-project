"""Read-only model/capability registry with a strict reproducibility gate."""

from __future__ import annotations

from copy import deepcopy
from functools import lru_cache
import importlib.util
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any


from app.config import PROJECT_ROOT  # honours MEDTWIN_PROJECT_ROOT (the container layout differs)

REGISTRY_PATH = Path(
    os.getenv("MODEL_REGISTRY_PATH", str(PROJECT_ROOT / "model_registry" / "models.json"))
)

ALLOWED_STATUSES = {
    "DISCOVERED",
    "NOT_INSTALLED",
    "DEPENDENCY_MISSING",
    "WEIGHTS_MISSING",
    "READY_UNVALIDATED",
    "VALIDATED",
    "FAILED",
    "UNSUPPORTED",
}

REQUIRED_BUNDLE_FIELDS = (
    "dataset_version",
    "dataset_license",
    "split_manifest_path",
    "task_definition",
    "label_definition",
    "preprocessing_version",
    "checkpoint_path",
    "checkpoint_sha256",
    "calibration",
    "decision_thresholds",
    "abstention_thresholds",
    "held_out_predictions_path",
    "evaluation_report_path",
    "model_card_path",
)

ARTIFACT_PATH_FIELDS = (
    "split_manifest_path",
    "checkpoint_path",
    "held_out_predictions_path",
    "evaluation_report_path",
    "model_card_path",
)


class RegistryConfigurationError(RuntimeError):
    """Raised when a source-controlled registry manifest is internally invalid."""


def _artifact_path_exists(value: str) -> bool:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = PROJECT_ROOT / candidate
    return candidate.exists() and candidate.is_file()


def _resolve_artifact_path(value: str) -> Path:
    candidate = Path(value)
    return candidate if candidate.is_absolute() else PROJECT_ROOT / candidate


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _validate_registry(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("schema_version") != "1.0.0":
        raise RegistryConfigurationError("Unsupported model-registry schema version.")
    models = payload.get("models")
    if not isinstance(models, list):
        raise RegistryConfigurationError("Model registry must contain a models array.")

    identifiers: set[str] = set()
    for index, model in enumerate(models):
        model_id = model.get("model_id")
        if not isinstance(model_id, str) or not model_id:
            raise RegistryConfigurationError(f"Model at index {index} has no model_id.")
        if model_id in identifiers:
            raise RegistryConfigurationError(f"Duplicate model_id: {model_id}")
        identifiers.add(model_id)
        if model.get("status") not in ALLOWED_STATUSES:
            raise RegistryConfigurationError(f"Invalid status for model {model_id}.")
        bundle = model.get("artifact_bundle")
        if not isinstance(bundle, dict):
            raise RegistryConfigurationError(f"Model {model_id} has no artifact_bundle object.")
        absent_keys = [field for field in REQUIRED_BUNDLE_FIELDS if field not in bundle]
        if absent_keys:
            raise RegistryConfigurationError(
                f"Model {model_id} artifact bundle omits keys: {', '.join(absent_keys)}"
            )
    return payload


@lru_cache(maxsize=1)
def _load_registry() -> dict[str, Any]:
    try:
        payload = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RegistryConfigurationError(f"Cannot load model registry: {exc}") from exc
    return _validate_registry(payload)


def activation_gate(model: dict[str, Any]) -> dict[str, Any]:
    """Return why a model can or cannot be activated; never mutate the manifest."""
    bundle = model["artifact_bundle"]
    missing_fields = [
        field
        for field in REQUIRED_BUNDLE_FIELDS
        if bundle.get(field) is None or bundle.get(field) == "" or bundle.get(field) == {}
    ]
    missing_artifacts = [
        field
        for field in ARTIFACT_PATH_FIELDS
        if bundle.get(field) and not _artifact_path_exists(str(bundle[field]))
    ]
    checkpoint_hash = bundle.get("checkpoint_sha256")
    hash_valid = bool(
        isinstance(checkpoint_hash, str)
        and re.fullmatch(r"[a-fA-F0-9]{64}", checkpoint_hash)
    )
    checkpoint_path = bundle.get("checkpoint_path")
    checkpoint_hash_matches = False
    if hash_valid and checkpoint_path and _artifact_path_exists(str(checkpoint_path)):
        checkpoint_hash_matches = _sha256(_resolve_artifact_path(str(checkpoint_path))) == checkpoint_hash.lower()
    status_valid = model.get("status") == "VALIDATED"
    validation_flag = model.get("validated") is True
    processor_only = model.get("processor_only") is True

    blockers: list[str] = []
    if processor_only:
        blockers.append("PROCESSOR_ONLY_NOT_ACTIVATABLE_AS_MODEL")
    if not status_valid:
        blockers.append("STATUS_NOT_VALIDATED")
    if not validation_flag:
        blockers.append("VALIDATION_FLAG_FALSE")
    if missing_fields:
        blockers.append("ARTIFACT_BUNDLE_INCOMPLETE")
    if checkpoint_hash is not None and not hash_valid:
        blockers.append("CHECKPOINT_HASH_INVALID")
    if hash_valid and checkpoint_path and not checkpoint_hash_matches:
        blockers.append("CHECKPOINT_HASH_MISMATCH")
    dataset_license = str(bundle.get("dataset_license") or "").strip().upper()
    if dataset_license in {"", "UNKNOWN", "UNVERIFIED"}:
        blockers.append("DATASET_LICENSE_UNVERIFIED")
    if missing_artifacts:
        blockers.append("ARTIFACT_FILES_MISSING")

    return {
        "eligible": not blockers,
        "blockers": blockers,
        "missing_fields": missing_fields,
        "missing_artifacts": missing_artifacts,
        "required_status": "VALIDATED",
        "current_status": model.get("status"),
        "validated": validation_flag,
        "checkpoint_hash_matches": checkpoint_hash_matches,
    }


REGISTRY_STATES = (
    "DISCOVERED",
    "DEPENDENCY_MISSING",
    "CHECKPOINT_MISSING",
    "READY_UNVALIDATED",
    "VALIDATED_FOR_TASK",
    "VALIDATED_FOR_RESEARCH_USE",
    "FAILED",
    "UNSUPPORTED",
    "LICENSE_BLOCKED",
    "INSUFFICIENT_DATA",
    "INSUFFICIENT_HARDWARE",
)


def registry_state(model: dict[str, Any], gate: dict[str, Any]) -> str:
    """Map the manifest status onto the MedTwin 2.0 registry vocabulary."""
    state = {"NOT_INSTALLED": "DEPENDENCY_MISSING", "WEIGHTS_MISSING": "CHECKPOINT_MISSING", "VALIDATED": "VALIDATED_FOR_TASK"}.get(model["status"], model["status"])
    if state == "VALIDATED_FOR_TASK" and "DATASET_LICENSE_UNVERIFIED" in gate["blockers"]:
        return "LICENSE_BLOCKED"
    return state


def list_models() -> dict[str, Any]:
    from app.services.model_inference import evaluation_summary, research_gate

    payload = deepcopy(_load_registry())
    for model in payload["models"]:
        model["activation"] = activation_gate(model)
        model["registry_state"] = registry_state(model, model["activation"])
        if model.get("research_inference"):
            # Research-only use is a separate, weaker gate than clinical activation.
            model["research_gate"] = research_gate(model)
            if model["research_gate"]["allowed"]:
                model["held_out_evaluation"] = evaluation_summary(model)
    payload["model_count"] = len(payload["models"])
    payload["activatable_count"] = sum(
        1 for model in payload["models"] if model["activation"]["eligible"]
    )
    return payload


def get_model(model_id: str) -> dict[str, Any] | None:
    for model in list_models()["models"]:
        if model["model_id"] == model_id:
            return model
    return None


def _module_available(module_name: str) -> bool:
    try:
        return importlib.util.find_spec(module_name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        return False


def scispacy_mode() -> str:
    from app.services.scispacy_adapter import mode

    return mode()


def _research_image_models_capability() -> dict[str, Any]:
    from app.services.model_inference import inference_models

    runnable = [model["model_id"] for model in inference_models() if model["gate"]["allowed"] and model["inference_input"] == "image_2d"]
    return {
        "capability_id": "research_image_models",
        "label": "Research-only 2D image models (public-dataset training)",
        "operational": bool(runnable),
        "verification_status": "INTERNAL_HELD_OUT_EVALUATION_ONLY",
        "runnable_models": runnable,
        "limitations": ["Trained and evaluated on public datasets with internal held-out splits; no external or clinical validation.",
                        "Input applicability is declared by the user; no out-of-distribution detection.",
                        "Outputs stay pending human review and are not mapped onto patient anatomy."],
    }


def get_capabilities() -> dict[str, Any]:
    """Expose executable boundaries independently from model readiness."""
    models = {item["model_id"]: item for item in list_models()["models"]}
    capabilities = [
        {
            "capability_id": "document_parsing",
            "label": "Medical document parsing",
            "operational": True,
            "verification_status": "IMPLEMENTED_AND_TESTED",
            "supports": ["TXT", "PDF_WITH_EMBEDDED_TEXT", "PDF_IMAGE_ONLY_VIA_LOCAL_OCR", "DOCX"],
            "limitations": ["Local OCR (RapidOCR/ONNX Runtime at 300 DPI) is used for pages without embedded text; "
                            "OCR text is marked per page and its extraction accuracy is not validated."],
        },
        {
            "capability_id": "clinical_text_rules",
            "label": "Transparent clinical-text extraction",
            "operational": True,
            "verification_status": "IMPLEMENTED_NOT_VALIDATED",
            "model_status": models["clinical_rules_v1"]["status"],
            "limitations": models["clinical_rules_v1"]["limitations"],
        },
        {
            "capability_id": "image_preprocessing",
            "label": "Medical image validation and preprocessing",
            "operational": True,
            "verification_status": "IMPLEMENTED_AND_TESTED",
            "inference_operational": False,
            "limitations": ["No validated image checkpoint is configured."],
        },
        _research_image_models_capability(),
        {
            "capability_id": "ecg_quality_preview",
            "label": "Digital ECG quality validation and preview",
            "operational": True,
            "verification_status": "IMPLEMENTED_AND_TESTED",
            "inference_operational": False,
            "limitations": ["No validated ECG checkpoint is configured."],
        },
        {
            "capability_id": "generic_anatomy_l1",
            "label": "Generic L1 anatomical GLB reference",
            "operational": True,
            "verification_status": "IMPLEMENTED_NOT_VALIDATED",
            "limitations": ["Generic reference only; no patient registration or L3 reconstruction."],
        },
        {
            "capability_id": "longitudinal_comparison",
            "label": "Evidence-preserving longitudinal comparison",
            "operational": True,
            "verification_status": "IMPLEMENTED_AND_TESTED",
            "limitations": ["Only compatible, explicitly represented measurements may be compared."],
        },
        {
            "capability_id": "multimodal_fusion",
            "label": "Paired multimodal fusion",
            "operational": False,
            "verification_status": "PROPOSED_ONLY",
            "limitations": ["No genuinely paired dataset or validated fusion model is registered."],
        },
        {
            "capability_id": "patient_registration",
            "label": "Patient-specific anatomical registration",
            "operational": False,
            "verification_status": "RESEARCH_GATE_NOT_ACTIVATED",
            "limitations": [
                "TRE mathematics is testable, but no reviewed patient landmark manifest, independently held-out landmark set, or patient geometry is registered."
            ],
        },
        {
            "capability_id": "monai_framework",
            "label": "MONAI framework adapter",
            "operational": _module_available("monai"),
            "verification_status": "SOURCE_SMOKE_TEST_ONLY",
            "model_status": models["monai_runtime"]["status"],
            "limitations": models["monai_runtime"]["limitations"],
        },
        {
            "capability_id": "medcat",
            "label": "MedCAT concept annotation",
            "operational": _module_available("medcat"),
            "verification_status": "NOT_INSTALLED",
            "model_status": models["medcat_adapter"]["status"],
            "limitations": models["medcat_adapter"]["limitations"],
        },
        {
            "capability_id": "scispacy",
            "label": "scispaCy biomedical NER (secondary, WSL)",
            "operational": scispacy_mode() == "wsl",
            "verification_status": "IMPLEMENTED_TESTED_NOT_VALIDATED" if scispacy_mode() == "wsl" else "DISABLED",
            "model_status": models["scispacy_adapter"]["status"],
            "limitations": models["scispacy_adapter"]["limitations"],
        },
        {
            "capability_id": "radgraph",
            "label": "RadGraph relation extraction",
            "operational": False,
            "verification_status": "DEPENDENCIES_AND_WEIGHTS_MISSING",
            "model_status": models["radgraph_adapter"]["status"],
            "limitations": models["radgraph_adapter"]["limitations"],
        },
    ]
    return {
        "schema_version": "1.0.0",
        "capability_count": len(capabilities),
        "operational_count": sum(1 for item in capabilities if item["operational"]),
        "capabilities": capabilities,
    }
