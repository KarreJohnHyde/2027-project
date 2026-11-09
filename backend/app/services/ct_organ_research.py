"""CT organ segmentation with TotalSegmentator v2 (third-party, published weights), as a research finding.

TotalSegmentator (Wasserthal et al., Radiology: AI 2023; Apache-2.0 code and 'total' weights) segments up to
117 structures on CT. MedTwin did not train it. Its weights were downloaded with the owner's approval into
artifacts/third_party/totalsegmentator; TotalSegmentator's usage statistics are switched off in its own
config before every run. Output: per-structure voxel masks in the upload's own voxel grid (the same
volume_segmentation format as the cardiac model, so masks overlay the slices and surfaces can be built),
a finding pending human review, never a diagnosis.

Applicability: a 3-D NIfTI whose voxel values look like Hounsfield units (air near -1000, soft tissue and
bone above it) with plausible CT spacing. MRI and other images are refused before the network runs.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import numpy as np
from sqlalchemy.orm import Session

from app.config import PROJECT_ROOT
from app.models.entities import (EvidenceStatus, Finding, InferenceRun, ModalityType, RepresentationLevel, UploadedFile, User)
from app.services import upload_store
from app.services.audit_service import log_audit_event

MODEL_ID = "ct_totalsegmentator_v2"
DISPLAY_NAME = "CT organ segmentation, up to 117 structures (TotalSegmentator v2, third-party)"
OUTPUT_STATUS = "RESEARCH_ONLY_THIRD_PARTY_PRETRAINED"
HOME = PROJECT_ROOT / "artifacts" / "third_party" / "totalsegmentator"
WEIGHTS = HOME / "weights"
FULL_PARTS = ("Dataset291_TotalSegmentator_part1_organs_1559subj", "Dataset292_TotalSegmentator_part2_vertebrae_1532subj",
              "Dataset293_TotalSegmentator_part3_cardiac_1559subj", "Dataset294_TotalSegmentator_part4_muscles_1559subj",
              "Dataset295_TotalSegmentator_part5_ribs_1559subj")
FAST_PART = "Dataset297_TotalSegmentator_total_3mm_1559subj"
PUBLISHER = {"name": "TotalSegmentator v2 (University Hospital Basel)", "version": "2.18.0 code, v2.0.0 'total' weights",
             "licence": "Apache-2.0 (code and the 'total' task weights)",
             "citation": "Wasserthal J, et al. TotalSegmentator: Robust Segmentation of 104 Anatomic Structures in CT Images. Radiol Artif Intell 2023;5(5):e230024.",
             "training_data": "1,559 CT examinations from University Hospital Basel (publisher's dataset); not LUNA16/LIDC-IDRI"}
SPACING_RANGE_MM = (0.2, 10.0)
MIN_SHAPE = (32, 32, 8)
# About 290 million voxels: a whole-body CT at 1 mm slices. The volume is read only after this header check.
MAX_VOXELS = 512 * 512 * 1100
SPATIAL_UNITS_TO_MM = {"mm": 1.0, "meter": 1000.0, "micron": 0.001}
LOCAL_CHECK = PROJECT_ROOT / "docs" / "validation" / "models" / "ct_totalsegmentator_v2.luna16_lungs.json"


class CtSegmentationUnavailable(Exception):
    """TotalSegmentator or its weights are not installed here."""


class CtNotApplicable(Exception):
    """The upload is not a CT volume TotalSegmentator can be applied to."""


def _weights_present(fast: bool) -> bool:
    parts = (FAST_PART,) if fast else FULL_PARTS
    return all(any((WEIGHTS / part).glob("*/fold_0/checkpoint_final.pth")) for part in parts)


def availability() -> dict[str, Any]:
    try:
        import totalsegmentator  # noqa: F401
    except ImportError:
        return {"available": False, "status": "DEPENDENCY_MISSING", "reason": "TotalSegmentator is not installed in this environment."}
    if not _weights_present(fast=True) and not _weights_present(fast=False):
        return {"available": False, "status": "WEIGHTS_MISSING", "reason": "TotalSegmentator weights are not in artifacts/third_party/totalsegmentator."}
    import torch

    return {"available": True, "status": "READY_UNVALIDATED", "full_resolution": _weights_present(fast=False), "fast": _weights_present(fast=True),
            "device": "cuda" if torch.cuda.is_available() else "cpu"}


def model_card() -> dict[str, Any]:
    local = json.loads(LOCAL_CHECK.read_text(encoding="utf-8")) if LOCAL_CHECK.exists() else None
    return {"model_id": MODEL_ID, "display_name": DISPLAY_NAME, **availability(), "publisher": PUBLISHER, "output_status": OUTPUT_STATUS,
            "local_external_check": local}


def _configure() -> None:
    """TotalSegmentator reads its home and weights folders from the environment and phones home unless told not to."""
    os.environ["TOTALSEG_HOME_DIR"] = str(HOME / "home")
    os.environ["TOTALSEG_WEIGHTS_PATH"] = str(WEIGHTS)
    (HOME / "home").mkdir(parents=True, exist_ok=True)
    config = HOME / "home" / "config.json"
    settings = json.loads(config.read_text(encoding="utf-8")) if config.exists() else {"totalseg_id": "medtwin-local", "prediction_counter": 0}
    if settings.get("send_usage_stats") is not False:
        settings["send_usage_stats"] = False
        config.write_text(json.dumps(settings, indent=4), encoding="utf-8")


def check_ct(image) -> dict[str, Any]:
    """Applicability on the header, then on a strided sample of voxels (the full volume is not read here):
    a 3-D grid within the voxel budget, CT spacing in millimetres, and Hounsfield-unit values."""
    shape = tuple(int(size) for size in image.shape)
    if len(shape) == 4 and shape[3] == 1:
        shape = shape[:3]
    if len(shape) != 3:
        raise CtNotApplicable(f"a single 3-D volume is required; this NIfTI has shape {list(image.shape)}.")
    if any(size < minimum for size, minimum in zip(shape, MIN_SHAPE)):
        raise CtNotApplicable(f"the volume {list(shape)} is too small for whole-structure segmentation (at least {list(MIN_SHAPE)} voxels).")
    voxels = shape[0] * shape[1] * shape[2]
    if voxels > MAX_VOXELS:
        raise CtNotApplicable(f"the volume has {voxels:,} voxels, more than the {MAX_VOXELS:,} this server segments in one run.")
    unit = image.header.get_xyzt_units()[0]
    warnings = [] if unit in SPATIAL_UNITS_TO_MM else ["The NIfTI header records no spatial unit; millimetres are assumed."]
    factor = SPATIAL_UNITS_TO_MM.get(unit, 1.0)
    spacing = [float(value) * factor for value in image.header.get_zooms()[:3]]
    low, high = SPACING_RANGE_MM
    if not all(low <= value <= high for value in spacing):
        raise CtNotApplicable(f"voxel spacing {[round(value, 4) for value in spacing]} mm is outside {low}-{high} mm; check the header units.")
    steps = (max(1, shape[0] // 64), max(1, shape[1] // 64), max(1, shape[2] // 32))
    window = (slice(None, None, steps[0]), slice(None, None, steps[1]), slice(None, None, steps[2]))
    sample = np.asarray(image.dataobj[window] if len(image.shape) == 3 else image.dataobj[(*window, 0)], dtype=np.float32)
    p1, p99 = (float(value) for value in np.percentile(sample, (1, 99)))
    if not (p1 <= -500 and p99 >= 0):
        raise CtNotApplicable(f"voxel values (1st-99th percentile {p1:.0f} to {p99:.0f}) do not look like Hounsfield units; "
                              "CT has air near -1000 and soft tissue around 0-100. MRI and normalised images are refused.")
    return {"shape_ijk": list(shape), "voxel_spacing_mm": [round(value, 6) for value in spacing], "intensity_p1_p99": [round(p1, 1), round(p99, 1)],
            "spatial_unit": unit, "unit_factor_to_mm": factor, "warnings": warnings,
            "rule": f"3-D NIfTI, at most {MAX_VOXELS:,} voxels, spacing 0.2-10 mm, 1st percentile <= -500 and 99th percentile >= 0 (Hounsfield units)"}


def check_upload(file_record: UploadedFile) -> dict[str, Any]:
    """The request-time refusal: a current, case-bound upload whose header and voxel sample pass check_ct."""
    import nibabel as nib

    if not file_record.is_associated or file_record.withdrawn_at is not None:
        raise CtNotApplicable("the upload is withdrawn or not associated with the case.")
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        return check_ct(nib.load(str(plain)))


def prepared_image(image, checks: dict[str, Any]):
    """The checked volume in memory as a 3-D image whose header and affine are in millimetres."""
    import nibabel as nib

    data = np.asanyarray(image.dataobj).reshape(checks["shape_ijk"])
    affine = image.affine.copy()
    if checks["unit_factor_to_mm"] != 1.0:
        affine[:3, :] *= checks["unit_factor_to_mm"]
    prepared = nib.Nifti1Image(data, affine)
    prepared.header.set_xyzt_units("mm")
    return prepared


def _segment(image, fast: bool):
    """Runs TotalSegmentator in this process; returns the multilabel image in the input's voxel grid."""
    _configure()
    import torch
    from totalsegmentator.python_api import totalsegmentator

    return totalsegmentator(image, None, ml=True, fast=fast, quiet=True, device="gpu" if torch.cuda.is_available() else "cpu",
                            nr_thr_resamp=1, nr_thr_saving=1)


def label_output(labels: np.ndarray, names: dict[int, str], spacing: list[float], checks: dict[str, Any], fast: bool) -> dict[str, Any]:
    """volume_segmentation output: per-structure volumes and per-slice COCO RLE (slice k stored as labels[:, :, k].T)."""
    from pycocotools import mask as coco_mask

    voxel_ml = spacing[0] * spacing[1] * spacing[2] / 1000.0
    present = [int(value) for value in np.unique(labels) if value != 0]
    counts = np.bincount(labels.ravel(), minlength=max(present, default=0) + 1)
    structures = [{"class_index": index, "structure": names.get(index, f"class_{index}"), "voxels": int(counts[index]),
                   "volume_ml": round(int(counts[index]) * voxel_ml, 3)} for index in present]
    slices = []
    for k in range(labels.shape[2]):
        plane = labels[:, :, k].T
        segments = []
        for index in np.unique(plane):
            if index == 0:
                continue
            binary = np.asfortranarray((plane == index).astype(np.uint8))
            rle = coco_mask.encode(binary)
            segments.append({"class_index": int(index), "area_px": int(binary.sum()), "rle": {"size": rle["size"], "counts": rle["counts"].decode("ascii")}})
        slices.append({"slice_index": k, "segments": segments})
    return {"type": "volume_segmentation", "structures": structures, "slices": slices,
            "volume_shape_ijk": list(labels.shape), "voxel_spacing_mm": [round(value, 6) for value in spacing], "voxel_volume_ml": voxel_ml,
            "coordinate_space": "NIfTI voxel grid; slice k drawn on the viewer's axial index plane (rows j, columns i)",
            "encoding": "COCO RLE per structure per axial slice (column-major)",
            "numeric_precision": f"TotalSegmentator {'fast (3 mm)' if fast else 'full resolution (1.5 mm)'} model, resampled back to this grid",
            "volume_semantics": "Predicted voxel count x header voxel volume. A research measurement of the model's mask, not a clinical volumetry.",
            "held_out_volume_agreement": {}, "input_warnings": list(checks.get("warnings", [])), "input_checks": checks}


def execute(db: Session, file_record: UploadedFile, actor: Optional[User], fast: bool = True,
            segmenter: Optional[Callable[[Any, bool], Any]] = None) -> InferenceRun:
    """Segment one CT NIfTI upload and record the output as a finding pending human review."""
    import nibabel as nib

    from app.services.model_usage_policy import registered_model_usage_gate
    usage = registered_model_usage_gate(MODEL_ID)
    if not usage["allowed"]:
        raise CtSegmentationUnavailable(", ".join(usage["blockers"]))
    if segmenter is None:
        state = availability()
        if not state["available"] or not state["fast" if fast else "full_resolution"]:
            raise CtSegmentationUnavailable(state.get("reason") or f"the {'fast' if fast else 'full-resolution'} weights are not installed.")
    from totalsegmentator.map_to_binary import class_map

    started_at = datetime.now(timezone.utc)
    start = time.perf_counter()
    if not file_record.is_associated or file_record.withdrawn_at is not None:
        raise CtNotApplicable("the upload is withdrawn or not associated with the case.")
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        image = nib.load(str(plain))
        checks = check_ct(image)  # header and a voxel sample, before the volume is read
        image = prepared_image(image, checks)  # read while the temporary file exists
    result = (segmenter or _segment)(image, fast)
    labels = np.asanyarray(result.dataobj).astype(np.uint8)
    if labels.shape[:3] != tuple(checks["shape_ijk"]):
        raise CtSegmentationUnavailable(f"segmentation grid {list(labels.shape)} differs from the input {checks['shape_ijk']}.")
    output = label_output(labels.reshape(checks["shape_ijk"]), class_map["total"], checks["voxel_spacing_mm"], checks, fast)
    exec_ms = round((time.perf_counter() - start) * 1000, 2)
    local = json.loads(LOCAL_CHECK.read_text(encoding="utf-8")) if LOCAL_CHECK.exists() else None
    run = InferenceRun(case_id=file_record.case_id, file_id=file_record.id, modality=file_record.modality, model_name=MODEL_ID,
                       model_version="totalseg-2.18.0-v2.0.0-" + ("fast" if fast else "full"),
                       preprocessing_version="totalsegmentator-2.18.0: canonical orientation, resample to "
                                             + ("3 mm" if fast else "1.5 mm") + ", nnU-Net, resampled back to the input grid",
                       status=EvidenceStatus.COMPLETED, execution_time_ms=exec_ms, started_at=started_at, completed_at=datetime.now(timezone.utc))
    db.add(run)
    db.flush()
    present = len(output["structures"])
    finding = Finding(
        inference_run_id=run.id, case_id=file_record.case_id, modality=ModalityType.IMAGE,
        category="Research model output (CT organ segmentation, third-party)", label=f"TotalSegmentator: {present} structure(s) segmented"[:255],
        raw_confidence=None, calibration_status="NOT_APPLICABLE_SEGMENTATION_NO_PROBABILITIES",
        representation_level=RepresentationLevel.L1_GENERIC, anatomical_region=None,
        mapping_status="PATIENT_DERIVED_NATIVE_FRAME_UNREGISTERED: masks in the scan's own voxel grid; not registered to the anatomy atlas.",
        review_status=EvidenceStatus.PENDING_HUMAN_REVIEW, is_demo=False,
        evidence_provenance={
            "source": "MODEL_INFERENCE", "output_status": OUTPUT_STATUS, "model_id": MODEL_ID, "model_display_name": DISPLAY_NAME,
            "model_status": "READY_UNVALIDATED", "publisher": PUBLISHER, "mode": "fast_3mm" if fast else "full_1.5mm",
            "held_out_evaluation": None, "local_external_check": local, "declared_input_type": "CT",
            "applicability": "Declared a CT volume by the requesting user; header and voxel values checked (input_checks).",
            "source_file_sha256": file_record.file_hash, "output": output,
        },
    )
    db.add(finding)
    db.commit()
    log_audit_event(db=db, action="RESEARCH_INFERENCE_COMPLETED", resource_type="ANALYSIS_JOB", resource_id=str(run.id), user=actor,
                    details={"case_id": file_record.case_id, "file_id": file_record.id, "finding_id": finding.id, "model_id": MODEL_ID,
                             "declared_input_type": "CT", "mode": "fast" if fast else "full", "exec_time_ms": exec_ms})
    db.refresh(run)
    return run
