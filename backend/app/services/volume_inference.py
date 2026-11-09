"""NIfTI input for the volumetric research segmenters: applicability and inference.

Two trainers are served:

- ``volumetric-monai-unet-v1`` (ACDC cardiac cine MRI, ml_training.volumetric): native voxel
  grid, no resampling or reorientation, z-score over the non-zero voxels, sliding-window
  inference with the training patch size, overlap 0.25 and float16 autocast on CUDA. Uploads
  must be one 3-D frame with square in-plane pixels and the slice axis last.
- ``volumetric-monai-multichannel-v2`` (brain MRI, ml_training.volumetric_multichannel):
  co-registered sequences stacked in one 4-D NIfTI in a fixed order, cropped to the voxels
  that are non-zero in any sequence, z-scored per sequence, optionally resampled to the
  training spacing, segmented by a sliding window, and the class probabilities resampled
  back to the upload's own grid. The trainer imports these functions, so its held-out
  evaluation ran exactly this code.

An upload must match the development data in the respects the network depends on (channel
count, voxel spacing, matrix and, for skull-stripped brain data, the share of non-zero
voxels), as recorded in the model's input envelope. Anything else is refused with every
reason stated.

Predicted volumes are voxel counts times the header voxel volume. They are research model
output for one upload, reported next to the held-out agreement of the same model.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import numpy as np

# NIfTI xyzt_units spatial codes -> millimetres per unit (0 = not declared).
SPATIAL_UNIT_TO_MM = {1: 1000.0, 2: 1.0, 3: 1e-3}
RELATIVE_TOLERANCE = 1e-4
SQUARE_PIXEL_TOLERANCE = 1e-3
SLIDING_WINDOW_OVERLAP = 0.25  # as in ml_training.volumetric.evaluate_cases
MULTICHANNEL_TRAINER = "volumetric-monai-multichannel-v2"
MAX_RESAMPLED_VOXELS = 400 * 400 * 400  # per channel, after resampling to the training spacing
SUPPORTED_TRAINERS = {"volumetric-monai-unet-v1": {"norm": "batch"}, MULTICHANNEL_TRAINER: {"norm": "group"}}
CARDIAC_VOLUME_SEMANTICS = ("Predicted voxel count x header voxel volume for this frame. Not a clinical measurement; ejection fraction needs "
                            "end-diastolic and end-systolic frames of one acquisition and is not computed from single uploads.")


class VolumeInputError(ValueError):
    """The upload is not a frame the segmenter was developed on."""

    def __init__(self, codes: list[str], detail: str):
        super().__init__(f"{', '.join(codes)}: {detail}")
        self.codes = codes


@dataclass
class VolumeInput:
    image: np.ndarray  # float32, NIfTI voxel order (i, j, k); (channel, i, j, k) for multi-channel models
    spacing_mm: tuple[float, float, float]
    warnings: list[str] = field(default_factory=list)
    # A DICOM series permuted/flipped into the development orientation: how to return a mask to the series grid.
    reorientation: Optional[dict] = None

    @property
    def spatial_shape(self) -> tuple[int, int, int]:
        return tuple(int(value) for value in self.image.shape[-3:])


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
    channel_names = envelope.get("channels")
    if channel_names:
        expected = len(channel_names)
        if not ((len(shape) == 4 and shape[3] == expected) or (len(shape) == 3 and expected == 1)):
            raise VolumeInputError(["CHANNEL_COUNT_MISMATCH"], f"this model needs {expected} co-registered volume(s) stacked in one "
                                   f"NIfTI in the order {', '.join(channel_names)}; the upload has shape {list(shape)}")
        if min(shape[:3]) < 2:
            raise VolumeInputError(["NOT_A_3D_VOLUME"], f"array shape {list(shape)}")
    else:
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
    _check_geometry(dx, dy, dz, envelope)
    orientations = envelope.get("orientations")
    if orientations:
        # The network reads voxel arrays as stored (nothing is reoriented), so the axis layout must be one it was trained on.
        axcodes = "".join(nib.aff2axcodes(image.affine))
        if axcodes not in orientations:
            raise VolumeInputError(["ORIENTATION_OUTSIDE_DEVELOPMENT_SET"],
                                   f"voxel axes {axcodes}; development cases were stored as {', '.join(sorted(orientations))}. Nothing is reoriented.")
    data = np.asarray(image.dataobj, dtype=np.float32)
    if channel_names:
        # Sequences are stacked along the fourth NIfTI axis; the network takes them as (channel, i, j, k).
        data = np.ascontiguousarray(np.moveaxis(data, 3, 0)) if data.ndim == 4 else data[None]
    else:
        data = data.reshape(shape)
    return _checked_volume(data, (dx, dy, dz), envelope, warnings)


ITK_SUFFIXES = (".nrrd", ".mha")
# ITK physical space is LPS; NIfTI affines (and the development orientation codes) are RAS.
_LPS_TO_RAS = np.diag([-1.0, -1.0, 1.0])


def itk_axcodes(direction: np.ndarray, spacing: tuple[float, float, float], origin: tuple[float, float, float]) -> str:
    """The NIfTI orientation code (e.g. 'RAS') of an ITK image's first three index axes."""
    import nibabel as nib

    affine = np.eye(4)
    affine[:3, :3] = _LPS_TO_RAS @ (direction @ np.diag(spacing))
    affine[:3, 3] = _LPS_TO_RAS @ np.asarray(origin, dtype=float)
    return "".join(nib.aff2axcodes(affine))


def read_itk_volume(path: Path, envelope: dict) -> VolumeInput:
    """An NRRD or single-file MetaImage volume, read into the NIfTI voxel order (i, j, k = ITK x, y, z).

    The same channel, geometry, orientation and intensity checks as a NIfTI frame apply. Multi-sequence
    models take the sequences as vector components or as a fourth axis, in the model's channel order."""
    import SimpleITK as sitk

    from app.services.imaging_readers import ImagingReadError, _guard_size, check_attached_data

    try:
        check_attached_data(path)
        reader = sitk.ImageFileReader()
        reader.SetFileName(str(path))
        reader.ReadImageInformation()
        size = tuple(int(value) for value in reader.GetSize())
        components = int(reader.GetNumberOfComponents())
        _guard_size(int(np.prod(size)) * components * 8)
    except ImagingReadError as exc:
        raise VolumeInputError(["ITK_HEADER_REFUSED"], str(exc)) from exc
    except RuntimeError as exc:  # SimpleITK raises RuntimeError for unreadable files
        raise VolumeInputError(["ITK_UNREADABLE"], type(exc).__name__) from exc
    channel_names = envelope.get("channels") or []
    expected = len(channel_names) or 1
    dimension = len(size)
    if dimension == 4 and size[3] == 1 and components == 1:
        dimension, size = 3, size[:3]
    if dimension == 3 and components == expected:
        layout = "vector" if components > 1 else "scalar"
    elif dimension == 4 and components == 1 and size[3] == expected and channel_names:
        layout = "fourth_axis"
    elif dimension == 4 and not channel_names:
        raise VolumeInputError(["FOUR_D_VOLUME"], f"{size[3]} frames; upload a single cine frame (end-diastole or end-systole)")
    elif dimension not in (3, 4):
        raise VolumeInputError(["NOT_A_3D_VOLUME"], f"{dimension}-D image of size {list(size)}")
    else:
        raise VolumeInputError(["CHANNEL_COUNT_MISMATCH"], f"this model needs {expected} co-registered volume(s)"
                               + (f" in the order {', '.join(channel_names)}" if channel_names else "")
                               + f"; the upload has size {list(size)} with {components} component(s) per voxel")
    if min(size[:3]) < 2:
        raise VolumeInputError(["NOT_A_3D_VOLUME"], f"image size {list(size)}")
    try:
        image = reader.Execute()
    except RuntimeError as exc:
        raise VolumeInputError(["ITK_UNREADABLE"], type(exc).__name__) from exc
    full_dimension = image.GetDimension()
    spacing = tuple(float(value) for value in image.GetSpacing()[:3])
    direction = np.asarray(image.GetDirection(), dtype=float).reshape(full_dimension, full_dimension)[:3, :3]
    origin = tuple(float(value) for value in image.GetOrigin()[:3])
    dx, dy, dz = spacing
    _check_geometry(dx, dy, dz, envelope)
    orientations = envelope.get("orientations")
    if orientations:
        axcodes = itk_axcodes(direction, spacing, origin)
        if axcodes not in orientations:
            raise VolumeInputError(["ORIENTATION_OUTSIDE_DEVELOPMENT_SET"],
                                   f"voxel axes {axcodes}; development cases were stored as {', '.join(sorted(orientations))}. Nothing is reoriented.")
    array = sitk.GetArrayFromImage(image).astype(np.float32, copy=False)
    if layout == "scalar":
        data = np.ascontiguousarray(np.transpose(array.reshape(size[::-1]), (2, 1, 0)))  # (z, y, x) -> (i, j, k)
        if channel_names:
            data = data[None]
    elif layout == "vector":
        data = np.ascontiguousarray(np.transpose(array, (3, 2, 1, 0)))  # (z, y, x, c) -> (c, i, j, k)
    else:
        data = np.ascontiguousarray(np.transpose(array, (0, 3, 2, 1)))  # (t, z, y, x) -> (c, i, j, k)
    container = "NRRD" if path.name.lower().endswith(".nrrd") else "MetaImage"
    warnings = [f"ITK_CONTAINER: read from {container}; voxel order i, j, k = ITK x, y, z as in NIfTI, spacing in mm as ITK reports it"]
    return _checked_volume(data, spacing, envelope, warnings)


def series_axcodes(affine_lps: np.ndarray) -> str:
    """NIfTI orientation code of a series' (column, row, slice) axes from its DICOM LPS affine."""
    import nibabel as nib

    affine = np.eye(4)
    affine[:3, :] = _LPS_TO_RAS @ np.asarray(affine_lps, dtype=float)[:3, :]
    return "".join(nib.aff2axcodes(affine))


def from_series(volume: np.ndarray, spacing_mm: dict, envelope: dict, affine_lps: Optional[np.ndarray] = None) -> VolumeInput:
    """A volume assembled from a DICOM series (app.services.dicom_series: slices, rows, columns)
    in the voxel order the segmenter uses: i = column, j = row, k = slice along the normal, the
    same order the viewer draws NIfTI masks in. The same checks as for a NIfTI frame apply.

    When the development frames record a patient orientation (envelope "orientations") and the series' axes differ,
    the series is permuted and flipped into a development orientation: exact, no resampling. The model's mask is
    returned to the series grid with the inverse (``reorientation``)."""
    import nibabel.orientations as orient

    channel_names = envelope.get("channels") or []
    if len(channel_names) > 1:
        raise VolumeInputError(["CHANNEL_COUNT_MISMATCH"], f"a DICOM series holds one sequence; this model needs {len(channel_names)} "
                               f"co-registered sequences ({', '.join(channel_names)}) stacked in one 4-D NIfTI")
    spacing = (float(spacing_mm["column"]), float(spacing_mm["row"]), float(spacing_mm["slice"]))
    data = np.ascontiguousarray(np.transpose(np.asarray(volume, dtype=np.float32), (2, 1, 0)))
    orientations = envelope.get("orientations")
    reorientation = None
    if orientations and affine_lps is not None:
        current = series_axcodes(np.asarray(affine_lps, dtype=float))
        if current in orientations:
            warnings = [f"ORIENTATION: series axes {current}, as in the development frames; not reoriented"]
        else:
            target = sorted(orientations)[0]
            forward = orient.ornt_transform(orient.axcodes2ornt(current), orient.axcodes2ornt(target))
            data = np.ascontiguousarray(orient.apply_orientation(data, forward))
            spacing = tuple(spacing[int(np.nonzero(forward[:, 0] == axis)[0][0])] for axis in range(3))
            reorientation = {"from": current, "to": target, "inverse": orient.ornt_transform(orient.axcodes2ornt(target), orient.axcodes2ornt(current)).tolist()}
            warnings = [f"REORIENTED: series axes {current} permuted and flipped to the development orientation {target} (exact, no resampling); "
                        "the mask is returned to the series grid"]
    else:
        warnings = ["ORIENTATION_CONVENTION: series read with i = column, j = row, k = slice position along the normal; the development "
                    "NIfTI frames carry no orientation, so the cardiac model chooses the convention from the image content and checks it "
                    "in patient coordinates (input_content_check.axis_convention); other models assume this convention"]
    _check_geometry(*spacing, envelope)
    if channel_names:
        data = data[None]
    checked = _checked_volume(data, spacing, envelope, warnings)
    checked.reorientation = reorientation
    return checked


def to_series_grid(mask: np.ndarray, volume: VolumeInput) -> tuple[np.ndarray, VolumeInput]:
    """A mask predicted on a reoriented series, returned to the series grid, with the input described on that grid."""
    if volume.reorientation is None:
        return mask, volume
    import nibabel.orientations as orient

    inverse = np.asarray(volume.reorientation["inverse"], dtype=float)
    restored = np.ascontiguousarray(orient.apply_orientation(mask, inverse))
    spacing = tuple(volume.spacing_mm[int(np.nonzero(inverse[:, 0] == axis)[0][0])] for axis in range(3))
    return restored, VolumeInput(np.empty((0,), np.float32), spacing, volume.warnings, volume.reorientation)


SHORT_AXIS_MIN_OBLIQUITY_DEG = 15.0
SHORT_AXIS_MIN_SLICES = 6


def short_axis_plausibility(report: dict) -> dict:
    """What DICOM geometry can say about a cardiac short-axis cine stack, before a cardiac model sees it.

    A short-axis plane is perpendicular to the left ventricle's long axis, which runs obliquely through the chest,
    so its slice normal is far from every body axis; an axial, coronal or sagittal stack is refused. The view itself
    (short axis rather than another oblique plane) and the phase cannot be read from tags: the requester attests them."""
    issues, details = [], []
    tags = list(report.get("modality_tags") or [])
    if tags and tags != ["MR"]:
        issues.append("SERIES_MODALITY_NOT_MR")
        details.append(f"Modality tags {', '.join(tags)}")
    normal = np.asarray(report["slice_normal_lps"], dtype=float)
    normal = normal / np.linalg.norm(normal)
    obliquity = float(np.degrees(np.arccos(min(1.0, float(np.max(np.abs(normal)))))))
    if obliquity < SHORT_AXIS_MIN_OBLIQUITY_DEG:
        axis = ("sagittal (left-right normal)", "coronal (anterior-posterior normal)", "axial (head-foot normal)")[int(np.argmax(np.abs(normal)))]
        issues.append("SLICE_NORMAL_ALIGNED_WITH_BODY_AXIS")
        details.append(f"the slice normal is {obliquity:.1f} degrees from the nearest body axis, a {axis} stack; short-axis stacks are "
                       f"double-oblique (at least {SHORT_AXIS_MIN_OBLIQUITY_DEG:.0f} degrees required)")
    slices = int(report["shape_slices_rows_columns"][0])
    if slices < SHORT_AXIS_MIN_SLICES:
        issues.append("TOO_FEW_SLICES_FOR_SHORT_AXIS_STACK")
        details.append(f"{slices} slices; development stacks had at least {SHORT_AXIS_MIN_SLICES}")
    if issues:
        raise VolumeInputError(issues, "; ".join(details) + ".")
    return {"status": "PASSED", "slice_normal_obliquity_deg": round(obliquity, 1), "slices": slices, "modality_tags": tags,
            "checks": f"MR modality, slice normal at least {SHORT_AXIS_MIN_OBLIQUITY_DEG:.0f} degrees from every body axis, at least "
                      f"{SHORT_AXIS_MIN_SLICES} slices; the view and phase are attested by the requester."}


# Every way the development arrays' (i, j, k) could relate to a scanner series' (column, row, slice): a row/column
# transpose and a flip of each axis. Flips were training augmentations; the transpose was not.
ORIENTATION_VARIANTS = [(transpose, flip_i, flip_j, flip_k) for transpose in (False, True) for flip_i in (False, True)
                        for flip_j in (False, True) for flip_k in (False, True)]
CONVENTION_RULE = ("The model is run under all 16 axis conventions and each prediction is mapped back to the series grid. Eligible "
                   "conventions put the predicted right ventricle anterior-right of the left ventricle in the series' DICOM patient "
                   "coordinates (normal anatomy) and have a left-ventricle area that shrinks along the slice axis in their own frame "
                   "(base to apex, as in the development frames). Among them, the one whose right-ventricle direction from the left "
                   "ventricle, in its own frame, is closest to the development frames' direction is used.")


def _orient(array: np.ndarray, variant: tuple[bool, bool, bool, bool]) -> np.ndarray:
    transpose, *flips = variant
    out = np.swapaxes(array, -3, -2) if transpose else array
    for axis, flip in zip((-3, -2, -1), flips):
        if flip:
            out = np.flip(out, axis=axis)
    return np.ascontiguousarray(out)


def _unorient(mask: np.ndarray, variant: tuple[bool, bool, bool, bool]) -> np.ndarray:
    transpose, *flips = variant
    out = mask
    for axis, flip in zip((-3, -2, -1), flips):
        if flip:
            out = np.flip(out, axis=axis)
    return np.ascontiguousarray(np.swapaxes(out, -3, -2) if transpose else out)


def _dice(a: np.ndarray, b: np.ndarray) -> float:
    total = int(a.sum()) + int(b.sum())
    return 1.0 if total == 0 else 2.0 * float(np.logical_and(a, b).sum()) / total


def ventricle_direction_deg(mask: np.ndarray, spacing: tuple[float, float, float], rv_label: int, lv_label: int) -> Optional[float]:
    """In-plane direction (degrees, atan2 of the j and i millimetre offsets) from the LV centroid to the RV centroid."""
    rv, lv = np.argwhere(mask == rv_label), np.argwhere(mask == lv_label)
    if len(rv) == 0 or len(lv) == 0:
        return None
    offset = (rv.mean(axis=0) - lv.mean(axis=0))[:2] * np.asarray(spacing[:2], dtype=float)
    return float(np.degrees(np.arctan2(offset[1], offset[0])))


def area_trend(mask: np.ndarray, label: int) -> float:
    """Correlation between slice index and the label's area per slice (negative: shrinking along k)."""
    areas = (mask == label).reshape(-1, mask.shape[-1]).sum(axis=0).astype(float)
    present = areas > 0
    if present.sum() < 3 or float(np.std(areas[present])) == 0.0:
        return 0.0
    return float(np.corrcoef(np.nonzero(present)[0], areas[present])[0, 1])


def angle_offset(angle: float, reference: float) -> float:
    return float(((angle - reference + 180.0) % 360.0) - 180.0)


def right_anterior_component(mask: np.ndarray, affine_lps: np.ndarray, rv_label: int, lv_label: int) -> Optional[float]:
    """Millimetres by which the RV centroid lies right-anterior of the LV centroid in DICOM LPS (None without both)."""
    rv, lv = np.argwhere(mask == rv_label), np.argwhere(mask == lv_label)
    if len(rv) == 0 or len(lv) == 0:
        return None
    offset = np.asarray(affine_lps, dtype=float)[:3, :3] @ (rv.mean(axis=0) - lv.mean(axis=0))
    return float(np.dot(offset, np.array([-1.0, -1.0, 0.0]) / np.sqrt(2.0)))  # LPS: right is -x, anterior is -y


def choose_convention(network, payload: dict, device, volume: VolumeInput, prior: dict,
                      affine_lps: Optional[np.ndarray] = None) -> tuple[np.ndarray, dict]:
    """Choose the axis convention of a scanner series from its content and geometry (CONVENTION_RULE).

    ``affine_lps`` maps the series grid (i = column, j = row, k = slice) to DICOM patient coordinates; without it the
    anatomical side is not used. Returns the chosen convention's prediction on the series grid and every candidate."""
    rv_label, lv_label = int(prior["rv_label"]), int(prior["lv_label"])
    candidates = []
    for variant in ORIENTATION_VARIANTS:
        transpose = variant[0]
        dx, dy, dz = volume.spacing_mm
        oriented = VolumeInput(_orient(volume.image, variant), (dy, dx, dz) if transpose else (dx, dy, dz), list(volume.warnings))
        mask = predict(network, payload, device, oriented)
        direction = ventricle_direction_deg(mask, oriented.spacing_mm, rv_label, lv_label)
        restored = _unorient(mask, variant)
        side = None if affine_lps is None else right_anterior_component(restored, affine_lps, rv_label, lv_label)
        candidates.append({"variant": {"transpose_rows_columns": transpose, "flip_i": variant[1], "flip_j": variant[2], "flip_k": variant[3]},
                           "rv_direction_offset_deg": None if direction is None else round(angle_offset(direction, prior["rv_direction_deg"]), 1),
                           "lv_area_trend": round(area_trend(mask, lv_label), 3),
                           "rv_right_anterior_mm": None if side is None else round(side, 1), "_mask": restored})
    found = [item for item in candidates if item["rv_direction_offset_deg"] is not None]
    report = {"rule": CONVENTION_RULE, "development_rv_direction_deg": prior["rv_direction_deg"],
              "direction_limit_deg": prior["rv_direction_limit_deg"], "anatomical_side_used": affine_lps is not None,
              "held_out": prior.get("held_out"),
              "candidates": [{key: value for key, value in item.items() if not key.startswith("_")} for item in candidates]}
    if not found:
        raise VolumeInputError(["VENTRICLES_NOT_FOUND"], "no axis convention gives both a left- and a right-ventricle prediction")
    sided = [item for item in found if affine_lps is None or (item["rv_right_anterior_mm"] or 0.0) > 0]
    if not sided:
        raise VolumeInputError(["RIGHT_VENTRICLE_NOT_RIGHT_ANTERIOR_IN_ANY_CONVENTION"],
                               "under no axis convention is the predicted right ventricle anterior-right of the left ventricle in the series' "
                               "patient coordinates, as normal anatomy requires")
    shrinking = [item for item in sided if item["lv_area_trend"] < 0]
    if not shrinking:
        raise VolumeInputError(["SLICE_ORDER_NOT_BASE_TO_APEX_IN_ANY_CONVENTION"],
                               "under no eligible axis convention does the predicted left-ventricle area shrink along the slices, as it does from "
                               "base to apex in the development frames")
    best = min(shrinking, key=lambda item: abs(item["rv_direction_offset_deg"]))
    report["chosen"] = report["candidates"][candidates.index(best)]
    if abs(best["rv_direction_offset_deg"]) > float(prior["rv_direction_limit_deg"]):
        raise VolumeInputError(["VENTRICLE_LAYOUT_OUTSIDE_DEVELOPMENT_RANGE"],
                               f"the closest convention puts the right ventricle {abs(best['rv_direction_offset_deg']):.0f} degrees from its "
                               f"direction in the development frames (limit {prior['rv_direction_limit_deg']:.0f}); the in-plane rotation of this "
                               "series is not one the model was developed on")
    return best["_mask"], report


def right_ventricle_is_right_anterior(mask: np.ndarray, affine_lps: np.ndarray, rv_label: int, lv_label: int) -> dict:
    """In patient coordinates (DICOM LPS) the right ventricle lies anterior and to the right of the left ventricle.

    ``mask`` is on the series grid (i = column, j = row, k = slice), the index order of the series affine."""
    rv, lv = np.argwhere(mask == rv_label), np.argwhere(mask == lv_label)
    if len(rv) == 0 or len(lv) == 0:
        raise VolumeInputError(["VENTRICLES_NOT_FOUND"], "the prediction lacks a left or a right ventricle")
    to_patient = np.asarray(affine_lps, dtype=float)[:3, :3]
    offset = to_patient @ (rv.mean(axis=0) - lv.mean(axis=0))
    right_anterior = np.array([-1.0, -1.0, 0.0]) / np.sqrt(2.0)  # LPS: right is -x, anterior is -y
    projection = float(np.dot(offset, right_anterior))
    if projection <= 0:
        raise VolumeInputError(["RIGHT_VENTRICLE_NOT_RIGHT_ANTERIOR"],
                               "in the series' patient coordinates the predicted right ventricle is not anterior-right of the left ventricle, as "
                               "anatomy requires; the labels or the series geometry are wrong")
    return {"status": "PASSED", "rv_offset_from_lv_lps_mm": [round(float(value), 1) for value in offset],
            "right_anterior_component_mm": round(projection, 1),
            "check": "RV centroid minus LV centroid, in DICOM patient coordinates, has a positive right-anterior component."}


def _check_geometry(dx: float, dy: float, dz: float, envelope: dict) -> None:
    issues, details = [], []
    if not all(math.isfinite(value) and value > 0 for value in (dx, dy, dz)):
        raise VolumeInputError(["INVALID_VOXEL_SPACING"], f"pixdim {dx:g} x {dy:g} x {dz:g}")
    if envelope.get("in_plane_square_pixels", True) and abs(dx - dy) > SQUARE_PIXEL_TOLERANCE * max(dx, dy):
        issues.append("NONSQUARE_IN_PLANE_PIXELS")
        details.append(f"in-plane spacing {dx:g} x {dy:g} mm")
    if envelope.get("slice_axis_last", True) and dz <= max(dx, dy):
        issues.append("SLICE_AXIS_NOT_LAST")
        details.append(f"the third axis ({dz:g} mm) is not the slice axis; short-axis stacks have their thickest spacing last")
    if not (_inside(dx, envelope["in_plane_spacing_mm"]) and _inside(dy, envelope["in_plane_spacing_mm"])):
        bounds = envelope["in_plane_spacing_mm"]
        issues.append("IN_PLANE_SPACING_OUTSIDE_DEVELOPMENT_RANGE")
        details.append(f"in-plane {dx:g} x {dy:g} mm; development cases {bounds['min']:g}-{bounds['max']:g} mm")
    if not _inside(dz, envelope["slice_spacing_mm"]):
        bounds = envelope["slice_spacing_mm"]
        issues.append("SLICE_SPACING_OUTSIDE_DEVELOPMENT_RANGE")
        details.append(f"slice {dz:g} mm; development cases {bounds['min']:g}-{bounds['max']:g} mm")
    if issues:
        raise VolumeInputError(issues, "; ".join(details) + ". Nothing is resampled.")


def _checked_volume(data: np.ndarray, spacing: tuple[float, float, float], envelope: dict, warnings: list[str]) -> VolumeInput:
    shape = data.shape[-3:]
    if not np.all(np.isfinite(data)):
        raise VolumeInputError(["NON_FINITE_VOXELS"], "the volume contains NaN or infinite values")
    channels = data if data.ndim == 4 else data[None]
    names = envelope.get("channels") or ["volume"]
    for name, channel in zip(names, channels):
        if float(channel.max()) == float(channel.min()):
            raise VolumeInputError(["CONSTANT_VOLUME"], f"every voxel of {name} has the same value")
    occupancy = envelope.get("nonzero_fraction")
    if occupancy:
        # Development brain volumes are skull-stripped with a zero background; a head with skull and scalp, or a
        # volume with a non-zero background, has a very different share of non-zero voxels.
        fraction = float(np.any(channels != 0, axis=0).mean())
        margin = float(occupancy.get("margin", 0.0))
        if not occupancy["min"] - margin <= fraction <= occupancy["max"] + margin:
            raise VolumeInputError(["NONZERO_FRACTION_OUTSIDE_DEVELOPMENT_RANGE"],
                                   f"{fraction:.1%} of voxels are non-zero; development cases had {occupancy['min']:.1%}-{occupancy['max']:.1%} "
                                   f"(skull-stripped volumes with a zero background, margin {margin:.0%})")
    hounsfield = envelope.get("hu_percentiles")
    if hounsfield:
        # Development CT volumes are in Hounsfield units (air near -1000); an MRI, a rescaled export or a mask is not.
        low, high = ct_percentiles(channels[0])
        margin = float(hounsfield.get("margin_hu", 0.0))
        if not (hounsfield["p01"]["min"] - margin <= low <= hounsfield["p01"]["max"] + margin
                and hounsfield["p99"]["min"] - margin <= high <= hounsfield["p99"]["max"] + margin):
            raise VolumeInputError(["INTENSITY_OUTSIDE_CT_DEVELOPMENT_RANGE"],
                                   f"1st/99th intensity percentiles {low:.0f}/{high:.0f}; development CT volumes had {hounsfield['p01']['min']:.0f} to "
                                   f"{hounsfield['p01']['max']:.0f} and {hounsfield['p99']['min']:.0f} to {hounsfield['p99']['max']:.0f} HU "
                                   f"(margin {margin:.0f} HU). The volume does not look like CT in Hounsfield units.")
    matrix = envelope["matrix"]
    if not all(matrix[axis]["min"] <= size <= matrix[axis]["max"] for axis, size in zip(("i", "j", "k"), shape)):
        warnings.append(f"MATRIX_OUTSIDE_DEVELOPMENT_RANGE ({' x '.join(map(str, shape))})")
    return VolumeInput(data, spacing, warnings)


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


def normalise_channels(image: np.ndarray) -> np.ndarray:
    """Per-sequence z-score over that sequence's non-zero voxels, (channel, i, j, k)."""
    return np.stack([normalise(channel) for channel in image]).astype(np.float32, copy=False)


CT_INTENSITY = "ct_hu_window"


def normalise_ct(image: np.ndarray, spec: dict) -> np.ndarray:
    """CT in Hounsfield units: clip to the training foreground's 0.5-99.5 percentile window, then z-score with the
    training foreground mean and standard deviation (the numbers are recorded in the checkpoint's preprocessing)."""
    low, high = (float(value) for value in spec["ct_clip_hu"])
    mean, std = float(spec["ct_mean"]), float(spec["ct_std"])
    output = (np.clip(np.nan_to_num(image, nan=low), low, high) - mean) / (std if std > 1e-6 else 1.0)
    return output.astype(np.float32, copy=False)


def ct_percentiles(channel: np.ndarray) -> tuple[float, float]:
    """1st and 99th intensity percentiles on a regular subsample (every 4th voxel on each axis)."""
    sample = channel[::4, ::4, ::4] if min(channel.shape) >= 8 else channel
    low, high = np.percentile(sample, [1, 99])
    return float(low), float(high)


def foreground_box(image: np.ndarray) -> tuple[slice, slice, slice]:
    """Bounding box of the voxels that are non-zero in any channel; the whole grid when none is."""
    occupied = np.any(image != 0, axis=0)
    if not occupied.any():
        return tuple(slice(0, int(size)) for size in occupied.shape)
    box = []
    for axis in range(3):
        found = np.flatnonzero(occupied.any(axis=tuple(other for other in range(3) if other != axis)))
        box.append(slice(int(found[0]), int(found[-1]) + 1))
    return tuple(box)


def resampled_shape(shape, spacing, target) -> tuple[int, int, int]:
    return tuple(max(1, int(round(size * mm / goal))) for size, mm, goal in zip(shape, spacing, target))


def preprocess_multichannel(image: np.ndarray, spacing, spec: dict) -> tuple[np.ndarray, tuple[slice, slice, slice], tuple[int, int, int]]:
    """Crop, per-channel z-score and (if the model was trained at a fixed spacing) trilinear resampling.

    Returns the network input (channel, x, y, z), the crop box in the upload's grid and the cropped shape."""
    import torch
    import torch.nn.functional as F

    box = foreground_box(image) if spec.get("foreground_crop") else tuple(slice(0, int(size)) for size in image.shape[1:])
    cropped = image[(slice(None), *box)]
    normed = normalise_ct(cropped, spec) if spec.get("intensity") == CT_INTENSITY else normalise_channels(cropped)
    target = spec.get("target_spacing_mm")
    if target:
        size = resampled_shape(normed.shape[1:], spacing, target)
        if int(np.prod(size, dtype=np.int64)) > MAX_RESAMPLED_VOXELS:
            raise VolumeInputError(["RESAMPLED_VOLUME_TOO_LARGE"], f"resampling to {target} mm would give {' x '.join(map(str, size))} voxels")
        if size != tuple(normed.shape[1:]):
            with torch.no_grad():
                normed = F.interpolate(torch.from_numpy(np.ascontiguousarray(normed))[None], size=size, mode="trilinear",
                                       align_corners=False)[0].numpy()
    return np.ascontiguousarray(normed, dtype=np.float32), box, tuple(int(size) for size in cropped.shape[1:])


def predict_multichannel(network, payload: dict, device, image: np.ndarray, spacing) -> np.ndarray:
    """Label volume on the upload's own grid (zero outside the crop box)."""
    import torch
    import torch.nn.functional as F
    from monai.inferers import sliding_window_inference

    spec = payload["preprocessing"]
    array, box, cropped_shape = preprocess_multichannel(image, spacing, spec)
    tensor = torch.from_numpy(array[None]).to(device)
    with torch.no_grad():
        with torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
            logits = sliding_window_inference(tensor, roi_size=tuple(int(item) for item in payload["patch_size"]),
                                              sw_batch_size=int(spec["sw_batch_size"]), predictor=network,
                                              overlap=float(spec["sliding_window_overlap"]), mode=spec["sliding_window_mode"])
        probabilities = torch.softmax(logits.float(), dim=1)
        del logits
        if tuple(probabilities.shape[2:]) != cropped_shape:
            probabilities = F.interpolate(probabilities, size=cropped_shape, mode="trilinear", align_corners=False)
        labels = probabilities.argmax(1)[0].cpu().numpy().astype(np.uint8)
    full = np.zeros(image.shape[1:], dtype=np.uint8)
    full[box] = labels
    return full


def build_network(payload: dict):
    trainer = SUPPORTED_TRAINERS.get(payload.get("trainer_version"))
    if trainer is None:
        raise VolumeInputError(["UNSUPPORTED_TRAINER_VERSION"], str(payload.get("trainer_version")))
    params = payload["architecture"]
    if payload["trainer_version"] == MULTICHANNEL_TRAINER:
        from monai.networks.nets import SegResNet

        if params.get("name") != "monai.networks.nets.SegResNet":
            raise VolumeInputError(["UNSUPPORTED_ARCHITECTURE"], str(params.get("name")))
        return SegResNet(spatial_dims=3, init_filters=int(params["init_filters"]), in_channels=int(params["in_channels"]),
                         out_channels=int(params["out_channels"]), blocks_down=tuple(params["blocks_down"]),
                         blocks_up=tuple(params["blocks_up"]), dropout_prob=params.get("dropout_prob"))
    from monai.networks.nets import UNet

    return UNet(spatial_dims=params["spatial_dims"], in_channels=params["in_channels"], out_channels=params["out_channels"],
                channels=tuple(params["channels"]), strides=tuple(params["strides"]), num_res_units=params["num_res_units"], norm=trainer["norm"])


def predict(network, payload: dict, device, volume: VolumeInput) -> np.ndarray:
    import torch
    from monai.inferers import sliding_window_inference

    if payload.get("trainer_version") == MULTICHANNEL_TRAINER:
        return predict_multichannel(network, payload, device, volume.image, volume.spacing_mm)
    tensor = torch.from_numpy(normalise(volume.image)[None, None]).to(device)
    with torch.no_grad(), torch.autocast(device_type=device.type, dtype=torch.float16, enabled=device.type == "cuda"):
        logits = sliding_window_inference(tensor, roi_size=tuple(int(item) for item in payload["patch_size"]), sw_batch_size=1,
                                          predictor=network, overlap=SLIDING_WINDOW_OVERLAP, mode="constant")
    return logits.float().argmax(1)[0].cpu().numpy().astype(np.uint8)


SURFACE_SEMANTICS = ("Surfaces of this run's predicted mask (marching cubes at the 0.5 level, no smoothing), in the scan's own voxel "
                     "grid scaled by the header voxel spacing: x = i·sx, y = j·sy, z = k·sz millimetres. No orientation affine is applied "
                     "(the development frames carry none) and nothing is registered to the anatomy atlas; thick slices give stepped surfaces.")


def mask_from_output(output: dict) -> np.ndarray:
    """The label volume rebuilt from a stored volume_segmentation output (slice k is stored as mask[:, :, k].T)."""
    from pycocotools import mask as coco_mask

    volume = np.zeros(output["volume_shape_ijk"], dtype=np.uint8)
    for plane in output["slices"]:
        for segment in plane["segments"]:
            decoded = coco_mask.decode({"size": segment["rle"]["size"], "counts": segment["rle"]["counts"].encode("ascii")})
            volume[:, :, plane["slice_index"]][decoded.T > 0] = segment["class_index"]
    return volume


def structure_surfaces(output: dict) -> dict:
    """Per-structure triangle surfaces of a stored volumetric run, for a patient-derived 3-D view."""
    from skimage.measure import marching_cubes

    volume = mask_from_output(output)
    spacing = tuple(float(value) for value in output["voxel_spacing_mm"])
    # Whole-body CT grids (512 x 512 x hundreds) would give meshes of millions of triangles: above 256 voxels
    # per axis the marching-cubes step grows so the longest axis has about 192 samples. Small grids keep step 1.
    step = 1 if max(volume.shape) <= 256 else int(np.ceil(max(volume.shape) / 192))
    surfaces, skipped = [], []
    for structure in output["structures"]:
        binary = volume == structure["class_index"]
        voxels = int(binary.sum())
        if voxels < 8:
            continue
        # Crop to the structure's bounding box, found by per-axis reductions (no per-voxel coordinate list),
        # so the cost follows the structure, not the grid.
        bounds = [np.flatnonzero(binary.any(axis=tuple(other for other in range(3) if other != axis))) for axis in range(3)]
        lower = np.array([found[0] for found in bounds])
        upper = np.array([found[-1] + 1 for found in bounds])
        crop = binary[lower[0]:upper[0], lower[1]:upper[1], lower[2]:upper[2]]
        # The step can be no larger than the thinnest side. One empty plane is padded before the structure and,
        # after it, as many as make the sampling lattice (0, s, 2s, ...) end on an empty plane, so the mesh closes.
        local = max(1, min(step, min(crop.shape)))
        after = [int(np.ceil((size + 1) / local)) * local - size for size in crop.shape]
        padded = np.pad(crop, [(1, pad) for pad in after]).astype(np.float32)
        try:
            vertices, faces, _normals, _values = marching_cubes(padded, level=0.5, spacing=spacing, step_size=local)
        except (ValueError, RuntimeError):
            skipped.append(structure["structure"])
            continue
        vertices += (lower - 1) * np.array(spacing)  # the leading pad shifts coordinates by one voxel
        surfaces.append({"class_index": structure["class_index"], "structure": structure["structure"], "voxels": voxels,
                         "volume_ml": structure["volume_ml"], "triangles": int(len(faces)), "step_voxels": local,
                         "vertices_mm": np.round(vertices, 2).ravel().tolist(), "faces": faces.astype(int).ravel().tolist()})
    extent = [round(size * mm, 2) for size, mm in zip(volume.shape, spacing)]
    return {"frame": "VOXEL_GRID_SCALED_MM", "voxel_spacing_mm": list(spacing), "extent_mm": extent, "registered_to_atlas": False,
            "marching_cubes_step_voxels": step, "structures_without_surface": skipped,
            "anatomy_link_level": "PATIENT_DERIVED_NATIVE_FRAME_UNREGISTERED", "semantics": SURFACE_SEMANTICS, "surfaces": surfaces}


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
            "volume_semantics": payload.get("volume_semantics") or CARDIAC_VOLUME_SEMANTICS,
            "held_out_volume_agreement": held_out, "input_warnings": volume.warnings}


def held_out_agreement(report: dict) -> dict:
    """Bias and limits of agreement of predicted vs reference volumes on the internal test set."""
    indices = report.get("clinical_indices") or {}
    keep = {}
    for key, value in indices.items():
        if key.endswith("_ml") and isinstance(value, dict) and "bias" in value:
            keep[key] = {"n_patients": value.get("n_patients"), "bias_ml": value["bias"], "limits_of_agreement_ml": value.get("limits_of_agreement")}
    return keep
