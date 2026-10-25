"""Modality support registry.

File-format support and clinical model coverage are reported separately: a
file that can be opened is not a file that can be interpreted. Reader
availability is detected at runtime from installed libraries; model coverage
comes from the model registry, where no learned model is validated.
"""

from __future__ import annotations

import importlib.util
from typing import Any

from app.services.model_registry import list_models


def _available(module: str) -> bool:
    try:
        return importlib.util.find_spec(module) is not None
    except (ImportError, ValueError):
        return False


def _readers() -> dict[str, dict[str, Any]]:
    return {
        "DICOM": {"library": "pydicom", "available": _available("pydicom"), "extensions": [".dcm"], "upload_accepted": True},
        # A single DICOM object is readable, but MedTwin does not yet accept or
        # assemble a multi-file series. Report that distinction explicitly so
        # the registry cannot imply grouping that the pipeline does not perform.
        "DICOM_SERIES": {"library": "pydicom", "available": False, "extensions": ["multi-file .dcm series"], "upload_accepted": False, "note": "NOT IMPLEMENTED: no atomic multi-file upload, SeriesInstanceUID grouping, InstanceNumber ordering, or series-level completeness validation."},
        "NIFTI": {"library": "nibabel", "available": _available("nibabel"), "extensions": [".nii", ".nii.gz"], "upload_accepted": True, "note": "NIfTI-1 only; NIfTI-2 headers are rejected by the pre-load memory-safety guard."},
        "NRRD": {"library": "SimpleITK", "available": _available("SimpleITK"), "extensions": [".nrrd"], "upload_accepted": True},
        "METAIMAGE": {"library": "SimpleITK", "available": _available("SimpleITK"), "extensions": [".mha"], "upload_accepted": True, "note": "Detached-header .mhd/.raw pairs are not accepted; use single-file .mha."},
        "RASTER": {"library": "Pillow", "available": _available("PIL"), "extensions": [".png", ".jpg", ".jpeg", ".bmp"], "upload_accepted": True},
        "ECG_CSV": {"library": "numpy", "available": True, "extensions": [".csv"], "upload_accepted": True},
        "WFDB": {"library": "wfdb", "available": _available("wfdb"), "extensions": [".dat", ".hea"], "upload_accepted": True, "note": "Header and signal files are stored; WFDB decoding is not implemented."},
        "EDF": {"library": None, "available": False, "extensions": [".edf"], "upload_accepted": False},
        "PDF": {"library": "pypdf", "available": _available("pypdf"), "extensions": [".pdf"], "upload_accepted": True, "note": "Embedded text is extracted first; image-only or sparsely textual pages use optional local pypdfium2 rendering plus RapidOCR/ONNX Runtime when both dependencies are available. OCR coordinates are retained in rendered-page pixel space."},
        "DOCX": {"library": "python-docx", "available": _available("docx"), "extensions": [".docx"], "upload_accepted": True},
        "XLSX": {"library": "openpyxl", "available": _available("openpyxl"), "extensions": [".xlsx"], "upload_accepted": True, "note": "Read-only; cached cell values, formulas are not evaluated."},
        "TEXT": {"library": None, "available": True, "extensions": [".txt", ".md", ".csv"], "upload_accepted": True},
        "JSON": {"library": None, "available": True, "extensions": [".json"], "upload_accepted": True},
        "FHIR_R4": {"library": None, "available": True, "extensions": [".json"], "upload_accepted": True, "note": "Observation (incl. components) and DiagnosticReport conclusion; other resource types are ignored."},
        "HL7_V2": {"library": None, "available": False, "extensions": [".hl7"], "upload_accepted": False},
    }


RADIOLOGY_FORMATS = ["DICOM", "DICOM_SERIES", "NIFTI", "NRRD", "METAIMAGE"]
VOLUME_PREPROCESSING = ["Rescale slope/intercept", "Window/level display", "Voxel-index slice extraction", "Spacing and orientation metadata"]
RASTER_PREPROCESSING = ["Validation and decode", "8-bit display", "Resize/normalise for a model input (no model configured)"]
IMAGING_TASKS = ["Classification", "Detection", "Segmentation", "Measurement", "Registration"]

MODALITY_SPECS: tuple[dict[str, Any], ...] = (
    {"id": "CT", "label": "Computed tomography", "group": "RADIOLOGY", "dicom_codes": ["CT"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": IMAGING_TASKS},
    {"id": "MRI", "label": "Magnetic resonance imaging", "group": "RADIOLOGY", "dicom_codes": ["MR"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": IMAGING_TASKS},
    {"id": "XRAY", "label": "X-ray / digital radiography", "group": "RADIOLOGY", "dicom_codes": ["DX", "CR"], "formats": ["DICOM", "RASTER"], "preprocessing": VOLUME_PREPROCESSING[:2] + RASTER_PREPROCESSING[:2], "candidate_tasks": IMAGING_TASKS},
    {"id": "US", "label": "Ultrasound", "group": "RADIOLOGY", "dicom_codes": ["US"], "formats": ["DICOM", "RASTER"], "preprocessing": ["Frame extraction", "8-bit display"], "candidate_tasks": IMAGING_TASKS},
    {"id": "DOPPLER", "label": "Doppler ultrasound", "group": "RADIOLOGY", "dicom_codes": ["US"], "formats": ["DICOM", "RASTER"], "preprocessing": ["Frame extraction", "8-bit display"], "candidate_tasks": ["Flow measurement"], "unsupported_note": "Doppler spectra and velocity calibration are not parsed."},
    {"id": "PET", "label": "Positron emission tomography", "group": "RADIOLOGY", "dicom_codes": ["PT"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": ["SUV measurement", "Segmentation"], "unsupported_note": "SUV requires decay, dose and weight tags; SUV computation is not implemented."},
    {"id": "SPECT", "label": "SPECT / nuclear medicine", "group": "RADIOLOGY", "dicom_codes": ["NM"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": IMAGING_TASKS},
    {"id": "PET_CT", "label": "PET/CT", "group": "RADIOLOGY", "dicom_codes": ["PT", "CT"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": ["Fusion display", "SUV measurement"], "unsupported_note": "Cross-modality fusion display is not implemented."},
    {"id": "XA", "label": "Angiography", "group": "RADIOLOGY", "dicom_codes": ["XA"], "formats": ["DICOM"], "preprocessing": ["Frame extraction", "Window/level display"], "candidate_tasks": ["Stenosis assessment"]},
    {"id": "CTA", "label": "CT angiography", "group": "RADIOLOGY", "dicom_codes": ["CT"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": ["Vessel segmentation", "Stenosis assessment"]},
    {"id": "MRA", "label": "MR angiography", "group": "RADIOLOGY", "dicom_codes": ["MR"], "formats": RADIOLOGY_FORMATS, "preprocessing": VOLUME_PREPROCESSING, "candidate_tasks": ["Vessel segmentation"]},
    {"id": "MG", "label": "Mammography", "group": "RADIOLOGY", "dicom_codes": ["MG"], "formats": ["DICOM"], "preprocessing": VOLUME_PREPROCESSING[:2], "candidate_tasks": ["Detection", "Density assessment"]},
    {"id": "DENTAL", "label": "Dental imaging", "group": "RADIOLOGY", "dicom_codes": ["IO", "PX"], "formats": ["DICOM", "RASTER"], "preprocessing": VOLUME_PREPROCESSING[:2], "candidate_tasks": ["Detection"]},
    {"id": "RF", "label": "Fluoroscopy", "group": "RADIOLOGY", "dicom_codes": ["RF"], "formats": ["DICOM"], "preprocessing": ["Frame extraction", "Window/level display"], "candidate_tasks": ["Measurement"]},
    {"id": "ENDOSCOPY", "label": "Gastrointestinal endoscopy", "group": "SPECIALISED", "dicom_codes": ["ES"], "formats": ["RASTER", "DICOM"], "preprocessing": RASTER_PREPROCESSING, "candidate_tasks": ["Polyp detection", "Finding classification", "Segmentation"], "unsupported_note": "Endoscopic images carry no anatomical coordinates without procedure metadata."},
    {"id": "HISTOPATHOLOGY", "label": "Histopathology", "group": "SPECIALISED", "dicom_codes": ["SM"], "formats": ["RASTER"], "preprocessing": RASTER_PREPROCESSING, "candidate_tasks": ["Classification", "Segmentation"], "unsupported_note": "Whole-slide pyramidal formats are not supported."},
    {"id": "MICROSCOPY", "label": "Cell microscopy (haematology)", "group": "SPECIALISED", "dicom_codes": ["GM"], "formats": ["RASTER"], "preprocessing": RASTER_PREPROCESSING, "candidate_tasks": ["Cell classification"], "unsupported_note": "Inputs are single segmented cells; whole smears and slide images are not supported."},
    {"id": "DERMATOLOGY", "label": "Dermatology photography", "group": "SPECIALISED", "dicom_codes": ["XC"], "formats": ["RASTER"], "preprocessing": RASTER_PREPROCESSING, "candidate_tasks": ["Classification"]},
    {"id": "RETINAL", "label": "Ophthalmic retinal imaging", "group": "SPECIALISED", "dicom_codes": ["OP", "OPT"], "formats": ["RASTER", "DICOM"], "preprocessing": RASTER_PREPROCESSING, "candidate_tasks": ["Classification", "Segmentation"]},
    {"id": "ECHO", "label": "Echocardiography", "group": "SPECIALISED", "dicom_codes": ["US"], "formats": ["DICOM"], "preprocessing": ["Frame extraction"], "candidate_tasks": ["Chamber segmentation", "Ejection fraction"], "unsupported_note": "Cine loops are rendered frame by frame only; ejection fraction is never estimated from a single image."},
    {"id": "ECG", "label": "Electrocardiogram", "group": "SIGNAL", "dicom_codes": ["ECG"], "formats": ["ECG_CSV", "WFDB"], "preprocessing": ["Signal quality checks", "Preview"], "candidate_tasks": ["Rhythm classification"]},
    {"id": "EEG", "label": "Electroencephalogram", "group": "SIGNAL", "dicom_codes": [], "formats": ["EDF"], "preprocessing": [], "candidate_tasks": ["Event detection"]},
    {"id": "DOCUMENT", "label": "Clinical documents", "group": "DOCUMENT", "dicom_codes": [], "formats": ["PDF", "DOCX", "XLSX", "TEXT", "JSON"], "preprocessing": ["Text extraction", "De-identification masking", "Section detection"], "candidate_tasks": ["Entity extraction", "Assertion and temporality", "Measurement extraction"]},
    {"id": "FHIR", "label": "FHIR R4 resources", "group": "INTEROPERABILITY", "dicom_codes": [], "formats": ["FHIR_R4"], "preprocessing": ["Observation rendering with source spans"], "candidate_tasks": ["Structured measurement import"]},
    {"id": "HL7V2", "label": "HL7 v2 messages", "group": "INTEROPERABILITY", "dicom_codes": [], "formats": ["HL7_V2"], "preprocessing": [], "candidate_tasks": ["Structured import"]},
)


# Registry entries name their modalities explicitly; a few use clinical words for a spec id.
MODALITY_ALIASES = {"ANGIOGRAPHY": "XA"}


def _model_candidates(models: list[dict[str, Any]], spec: dict[str, Any]) -> list[dict[str, Any]]:
    """Models whose registry entry declares this modality (keyword matching listed unrelated models)."""
    found = []
    for model in models:
        declared = {MODALITY_ALIASES.get(item, item) for item in model.get("supported_modalities", [])}
        if spec["id"] in declared:
            found.append({"model_id": model["model_id"], "display_name": model["display_name"], "status": model["status"],
                          "activation_eligible": model["activation"]["eligible"], "research_inference": bool(model.get("research_gate", {}).get("allowed"))})
    return found


def modality_registry() -> dict[str, Any]:
    readers = _readers()
    models = list_models()["models"]
    entries = []
    for spec in MODALITY_SPECS:
        formats = [{"format": name, **readers[name]} for name in spec["formats"]]
        readable = any(item["available"] and item["upload_accepted"] for item in formats)
        candidates = _model_candidates(models, spec)
        validated = [item for item in candidates if item["activation_eligible"]]
        entries.append({
            "id": spec["id"],
            "label": spec["label"],
            "group": spec["group"],
            "dicom_modality_codes": spec["dicom_codes"],
            "supported_file_formats": formats,
            "file_support_status": "SUPPORTED" if readable else "UNSUPPORTED_MODALITY",
            "supported_preprocessing": spec["preprocessing"] if readable else [],
            "available_ai_models": candidates,
            "validated_tasks": [task for task in spec["candidate_tasks"] if validated],
            "unsupported_tasks": [{"task": task, "status": "MODEL_NOT_VALIDATED"} for task in spec["candidate_tasks"]] if not validated else [],
            "extraction_status": "RULE_BASELINE_UNVALIDATED" if spec["id"] == "DOCUMENT" else None,
            "notes": [spec["unsupported_note"]] if spec.get("unsupported_note") else [],
        })
    return {
        "schema_version": "medtwin-modality-registry-1.0.0",
        "notice": "Opening a file is not interpreting it. Clinical tasks activate only through a validated model in the model registry.",
        "modalities": entries,
        "readers": readers,
    }
