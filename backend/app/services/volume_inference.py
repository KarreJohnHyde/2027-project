"""Cardiac cine-MRI NIfTI input for the ACDC research segmenter: applicability and inference.

The network was trained and evaluated on the native voxel grid (ml_training.volumetric):
no resampling or reorientation, z-score over the non-zero voxels, sliding-window
inference with the training patch size, overlap 0.25 and float16 autocast on CUDA. An
upload must therefore match the development data in the respects the network depends on:
one 3-D frame, square in-plane pixels, the slice axis last, and voxel spacing inside the
range of the development cases recorded in the model's input envelope. Anything else is
refused with every reason stated.

Predicted volumes are voxel counts times the header voxel volume. They are research model
output for one frame, reported next to the held-out agreement of the same model.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# NIfTI xyzt_units spatial codes -> millimetres per unit (0 = not declared).
SPATIAL_UNIT_TO_MM = {1: 1000.0, 2: 1.0, 3: 1e-3}
RELATIVE_TOLERANCE = 1e-4
SQUARE_PIXEL_TOLERANCE = 1e-3
SLIDING_WINDOW_OVERLAP = 0.25  # as in ml_training.volumetric.evaluate_cases
SUPPORTED_TRAINERS = {"volumetric-monai-unet-v1": {"norm": "batch"}}


class VolumeInputError(ValueError):
    """The upload is not a frame the segmenter was developed on."""

    def __init__(self, codes: list[str], detail: str):
        super().__init__(f"{', '.join(codes)}: {detail}")
        self.codes = codes


@dataclass
class VolumeInput:
    image: np.ndarray  # float32, NIfTI voxel order (i, j, k)
    spacing_mm: tuple[float, float, float]
    warnings: list[str] = field(default_factory=list)


def load_envelope(path: Path, dataset_version: str) -> dict:
    envelope = json.loads(path.read_text(encoding="utf-8"))
    if envelope.get("dataset_version") != dataset_version:
        raise VolumeInputError(["INPUT_ENVELOPE_MISMATCH"], "the recorded input envelope was derived from a different dataset version")
    return envelope


def _inside(value: float, bounds: dict) -> bool:
    return bounds["min"] * (1 - RELATIVE_TOLERANCE) <= value <= bounds["max"] * (1 + RELATIVE_TOLERANCE)


def read_volume(path: Path, envelope: dict) -> VolumeInput:
    import nibabel as nib

    try:
        image = nib.load(str(path))
    except Exception as exc:  # nibabel raises several types for malformed files
        raise VolumeInputError(["NIFTI_UNREADABLE"], type(exc).__name__) from exc
    shape = tuple(int(value) for value in image.shape)
    if len(shape) == 4 and shape[3] == 1:
        shape = shape[:3]
    if len(shape) == 4:
        raise VolumeInputError(["FOUR_D_VOLUME"], f"{shape[3]} frames; upload a single cine frame (end-diastole or end-systole)")
    if len(shape) != 3 or min(shape) < 2:
        raise VolumeInputError(["NOT_A_3D_VOLUME"], f"array shape {list(image.shape)}")
    header = image.header
    unit_code = int(header["xyzt_units"]) & 0x07
    warnings = []
    if unit_code == 0:
        warnings.append("SPATIAL_UNIT_NOT_DECLARED_TREATED_AS_MM (as in every development case)")
    elif unit_code not in SPATIAL_UNIT_TO_MM:
        raise VolumeInputError(["SPATIAL_UNIT_UNSUPPORTED"], f"xyzt_units spatial code {unit_code}")
    scale = SPATIAL_UNIT_TO_MM.get(unit_code, 1.0)
    dx, dy, dz = (float(value) * scale for value in header.get_zooms()[:3])

    issues, details = [], []
    if not all(math.isfinite(value) and value > 0 for value in (dx, dy, dz)):
        raise VolumeInputError(["INVALID_VOXEL_SPACING"], f"pixdim {dx:g} x {dy:g} x {dz:g}")
    if abs(dx - dy) > SQUARE_PIXEL_TOLERANCE * max(dx, dy):
        issues.append("NONSQUARE_IN_PLANE_PIXELS")
        details.append(f"in-plane spacing {dx:g} x {dy:g} mm")
    if dz <= max(dx, dy):
        issues.append("SLICE_AXIS_NOT_LAST")
        details.append(f"the third axis ({dz:g} mm) is not the slice axis; short-axis stacks have their thickest spacing last")
    if not _inside(dx, envelope["in_plane_spacing_mm"]):
        bounds = envelope["in_plane_spacing_mm"]
        issues.append("IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE")
        details.append(f"in-plane {dx:g} mm; development cases {bounds['min']:g}-{bounds['max']:g} mm")
    if not _inside(dz, envelope["slice_spacing_mm"]):
        bounds = envelope["slice_spacing_mm"]
        issues.append("SLICE_SPACING_OUTSIDE_DEVELOPMENT_RANGE")
        details.append(f"slice {dz:g} mm; development cases {bounds['min']:g}-{bounds['max']:g} mm")
    if issues:
        raise VolumeInputError(issues, "; ".join(details) + ". Nothing is resampled.")

    data = np.asarray(image.dataobj, dtype=np.float32).reshape(shape)
    if not np.all(np.isfinite(data)):
        raise VolumeInputError(["NON_FINITE_VOXELS"], "the volume contains NaN or infinite values")
    if float(data.max()) == float(data.min()):
        raise VolumeInputError(["CONSTANT_VOLUME"], "every voxel has the same value")
    matrix = envelope["matrix"]
    if not all(matrix[axis]["min"] <= size <= matrix[axis]["max"] for axis, size in zip(("i", "j", "k"), shape)):
        warnings.append(f"MATRIX_OUTSIDE_DEVELOPMENT_RANGE ({' x '.join(map(str, shape))})")
    return VolumeInput(data, (dx, dy, dz), warnings)


def normalise(image: np.ndarray) -> np.ndarray:
    """ml_training.volumetric._normalise: z-score over the non-zero voxels."""
    finite = np.isfinite(image)
    nonzero = finite & (image != 0)
    sample = image[nonzero] if int(nonzero.sum()) >= 8 else image[finite]
    mean = float(sample.mean()) if sample.size else 0.0
    std = float(sample.std()) if sample.size else 1.0
    if not math.isfinite(std) or std < 1e-6:
        std = 1.0
    output = (image - mean) / std
    output[~finite] = 0
    return output.astype(np.float32, copy=False)


def build_network(payload: dict):
    from monai.networks.nets import UNet

    trainer = SUPPORTED_TRAINERS.get(payload.get("trainer_version"))
    if trainer is None:
        raise VolumeInputError(["UNSUPPORTED_TRAINER_VERSION"], str(payload.get("trainer_version")))
    params = payload["architecture"]
    return UNet(spatial_dims=params["spatial_dims"], in_channels=params["in_channels"], out_channels=params["out_channels"],
                channels=tuple(params["channels"]), strides=tuple(params["strides"]), num_res_units=params["num_res_units"], norm=trainer["norm"])


def predict(network, payload: dict, device, volume: VolumeInput) -> np.ndarray:
    import torch
    from monai.inferers import sliding_window_inference

    tensor = torch.from_numpy(normalise(volume.image)[None, None]).to(device)
    with torch.no_grad(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
        logits = sliding_window_inference(tensor, roi_size=tuple(int(item) for item in payload["patch_size"]), sw_batch_size=1,
                                          predictor=network, overlap=SLIDING_WINDOW_OVERLAP, mode="constant")
    return logits.float().argmax(1)[0].cpu().numpy().astype(np.uint8)


def segmentation_output(mask: np.ndarray, payload: dict, volume: VolumeInput, held_out: dict[str, Any], device) -> dict:
    """Per-structure volumes and per-slice masks in the viewer's axial display pixels.

    The imaging viewer renders axial index plane k of a NIfTI as rows j and columns i
    (app.services.imaging_readers.render_slice), so each slice mask is mask[:, :, k].T."""
    from pycocotools import mask as coco_mask

    voxel_ml = volume.spacing_mm[0] * volume.spacing_mm[1] * volume.spacing_mm[2] / 1000.0
    structures, slices = [], []
    labels = [label for label in payload["labels"] if int(label["id"]) != 0]
    for label in labels:
        count = int((mask == int(label["id"])).sum())
        structures.append({"class_index": int(label["id"]), "structure": label["name"], "voxels": count, "volume_ml": round(count * voxel_ml, 3)})
    for k in range(mask.shape[2]):
        plane = mask[:, :, k].T
        segments = []
        for label in labels:
            binary = np.asfortranarray((plane == int(label["id"])).astype(np.uint8))
            area = int(binary.sum())
            if area:
                rle = coco_mask.encode(binary)
                segments.append({"class_index": int(label["id"]), "area_px": area, "rle": {"size": rle["size"], "counts": rle["counts"].decode("ascii")}})
        slices.append({"slice_index": k, "segments": segments})
    return {"type": "volume_segmentation", "structures": structures, "slices": slices,
            "volume_shape_ijk": list(mask.shape), "voxel_spacing_mm": [round(value, 6) for value in volume.spacing_mm], "voxel_volume_ml": voxel_ml,
            "coordinate_space": "NIfTI voxel grid; slice k drawn on the viewer's axial index plane (rows j, columns i)",
            "encoding": "COCO RLE per structure per axial slice (column-major)",
            "numeric_precision": "float16 autocast on CUDA, as in the held-out evaluation" if device.type == "cuda" else "float32 on CPU; differs from the evaluated float16 CUDA configuration",
            "volume_semantics": "Predicted voxel count x header voxel volume for this frame. Not a clinical measurement; ejection fraction needs end-diastolic and end-systolic frames of one acquisition and is not computed from single uploads.",
            "held_out_volume_agreement": held_out, "input_warnings": volume.warnings}


def held_out_agreement(report: dict) -> dict:
    """Bias and limits of agreement of predicted vs reference volumes on the internal test set."""
    indices = report.get("clinical_indices") or {}
    keep = {}
    for key, value in indices.items():
        if key.endswith("_ml") and isinstance(value, dict) and "bias" in value:
            keep[key] = {"n_patients": value.get("n_patients"), "bias_ml": value["bias"], "limits_of_agreement_ml": value.get("limits_of_agreement")}
    return keep
