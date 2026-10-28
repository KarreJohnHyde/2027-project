"""Multi-file DICOM series assembly with fail-closed geometry checks.

Slices are grouped by SeriesInstanceUID and ordered by their position along the slice normal
(ImagePositionPatient projected onto the cross product of the ImageOrientationPatient
cosines), never by InstanceNumber alone. A series is assembled only when every slice shares
one orientation, matrix and pixel spacing, positions are unique, and spacing is uniform with
no gap. The result carries the voxel-to-patient affine in DICOM LPS millimetres, mapping
(column i, row j, slice k) indices: x = origin + i*dc*row_dir + j*dr*col_dir + k*ds*normal.

Identifiers are never returned: series are referred to by a short SHA-256 of their UID, and
identifying tags are reported by keyword only so a reviewer can see de-identification gaps.
"""

from __future__ import annotations

import hashlib
import threading
from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Optional, Sequence

import numpy as np

from app.services.imaging_readers import IDENTIFYING_DICOM_KEYWORDS, MAX_VOXEL_BYTES

ORIENTATION_TOLERANCE = 1e-4  # direction-cosine difference
POSITION_TOLERANCE_MM = 1e-3  # two slices this close are the same position
GAP_FACTOR = 1.5  # a step this many times the median spacing means slices are missing
UNIFORMITY_TOLERANCE = 0.05  # relative spread of slice steps allowed without a gap
REJECTING_ISSUES = frozenset({
    "NO_DICOM_GEOMETRY", "MULTIPLE_SERIES", "SERIES_NOT_FOUND", "SINGLE_SLICE", "INCONSISTENT_ORIENTATION",
    "INCONSISTENT_MATRIX", "DUPLICATE_SLICE_POSITION", "MISSING_SLICES", "NONUNIFORM_SLICE_SPACING", "VOLUME_TOO_LARGE",
})


def uid_reference(uid: str) -> str:
    """A non-identifying handle for a DICOM UID."""
    return hashlib.sha256(uid.encode("utf-8")).hexdigest()[:16]


@dataclass
class SliceHeader:
    index: int  # position in the caller's input list
    series_uid: str
    instance_number: Optional[int]
    position: Optional[np.ndarray]
    orientation: Optional[np.ndarray]
    pixel_spacing: Optional[tuple[float, float]]
    rows: int
    columns: int
    identifying_tags: tuple[str, ...]


def read_header(path: Path, index: int) -> SliceHeader:
    import pydicom

    dataset = pydicom.dcmread(str(path), stop_before_pixels=True)
    position = getattr(dataset, "ImagePositionPatient", None)
    orientation = getattr(dataset, "ImageOrientationPatient", None)
    spacing = getattr(dataset, "PixelSpacing", None)
    return SliceHeader(
        index=index,
        series_uid=str(getattr(dataset, "SeriesInstanceUID", "")),
        instance_number=int(dataset.InstanceNumber) if getattr(dataset, "InstanceNumber", None) not in (None, "") else None,
        position=np.asarray([float(value) for value in position]) if position is not None and len(position) == 3 else None,
        orientation=np.asarray([float(value) for value in orientation]) if orientation is not None and len(orientation) == 6 else None,
        pixel_spacing=(float(spacing[0]), float(spacing[1])) if spacing is not None and len(spacing) == 2 else None,
        rows=int(getattr(dataset, "Rows", 0)),
        columns=int(getattr(dataset, "Columns", 0)),
        identifying_tags=tuple(keyword for keyword in IDENTIFYING_DICOM_KEYWORDS if str(getattr(dataset, keyword, "") or "").strip()),
    )


def assemble_series(paths: Sequence[Path], series_reference: Optional[str] = None, load_pixels: bool = False) -> dict[str, Any]:
    """Assemble one series from DICOM files. Returns a report; with load_pixels the report also
    holds the rescaled float32 volume (slices, rows, columns) under "volume"."""
    headers = [read_header(path, index) for index, path in enumerate(paths)]
    by_series: dict[str, list[SliceHeader]] = {}
    for header in headers:
        by_series.setdefault(header.series_uid, []).append(header)
    series_summary = [{"series_reference": uid_reference(uid), "slice_count": len(items)} for uid, items in sorted(by_series.items(), key=lambda item: -len(item[1]))]
    report: dict[str, Any] = {"status": "REJECTED", "issues": [], "warnings": [], "series": series_summary, "input_count": len(headers)}

    if series_reference is not None:
        chosen = [items for uid, items in by_series.items() if uid_reference(uid) == series_reference]
        if not chosen:
            report["issues"].append("SERIES_NOT_FOUND")
            return report
        slices = chosen[0]
    elif len(by_series) > 1:
        report["issues"].append("MULTIPLE_SERIES")
        return report
    else:
        slices = next(iter(by_series.values()), [])
    report["series_reference"] = uid_reference(slices[0].series_uid) if slices else None

    if len(slices) < 2:
        report["issues"].append("SINGLE_SLICE")
        return report
    if any(item.position is None or item.orientation is None or item.pixel_spacing is None for item in slices):
        report["issues"].append("NO_DICOM_GEOMETRY")
        return report

    orientation = slices[0].orientation
    if any(np.max(np.abs(item.orientation - orientation)) > ORIENTATION_TOLERANCE for item in slices):
        report["issues"].append("INCONSISTENT_ORIENTATION")
    if any((item.rows, item.columns, item.pixel_spacing) != (slices[0].rows, slices[0].columns, slices[0].pixel_spacing) for item in slices):
        report["issues"].append("INCONSISTENT_MATRIX")
    if report["issues"]:
        return report

    row_dir, col_dir = orientation[:3], orientation[3:]
    normal = np.cross(row_dir, col_dir)
    ordered = sorted(slices, key=lambda item: float(np.dot(item.position, normal)))
    along = np.asarray([float(np.dot(item.position, normal)) for item in ordered])
    steps = np.diff(along)
    if np.any(steps < POSITION_TOLERANCE_MM):
        report["issues"].append("DUPLICATE_SLICE_POSITION")
        return report
    median_step = float(np.median(steps))
    if np.any(steps > GAP_FACTOR * median_step):
        report["issues"].append("MISSING_SLICES")
    elif float(steps.max() - steps.min()) > UNIFORMITY_TOLERANCE * median_step:
        report["issues"].append("NONUNIFORM_SLICE_SPACING")
    if report["issues"]:
        report["slice_steps_mm"] = [round(float(step), 4) for step in steps]
        return report

    if any(item.instance_number is not None for item in ordered):
        numbers = [item.instance_number for item in ordered if item.instance_number is not None]
        if numbers != sorted(numbers) and numbers != sorted(numbers, reverse=True):
            report["warnings"].append("INSTANCE_NUMBER_ORDER_DISAGREES_WITH_POSITION")
    identifying = sorted({tag for item in ordered for tag in item.identifying_tags})
    if identifying:
        report["warnings"].append("IDENTIFYING_TAGS_PRESENT")

    row_spacing, column_spacing = ordered[0].pixel_spacing
    affine = np.eye(4)
    affine[:3, 0] = row_dir * column_spacing
    affine[:3, 1] = col_dir * row_spacing
    affine[:3, 2] = normal * median_step
    affine[:3, 3] = ordered[0].position
    shape = (len(ordered), ordered[0].rows, ordered[0].columns)
    if int(np.prod(shape)) * 4 > MAX_VOXEL_BYTES:
        report["issues"].append("VOLUME_TOO_LARGE")
        return report

    report.update(
        status="ASSEMBLED",
        shape_slices_rows_columns=list(shape),
        spacing_mm={"row": row_spacing, "column": column_spacing, "slice": round(median_step, 6)},
        orientation_cosines=[round(float(value), 6) for value in orientation],
        affine_lps_mm=[[round(float(value), 6) for value in row] for row in affine],
        affine_index_order="column i, row j, slice k",
        coordinate_system="DICOM_LPS",
        ordered_input_indices=[item.index for item in ordered],
        identifying_tags_present=identifying,
    )
    if load_pixels:
        import pydicom

        planes = []
        for item in ordered:
            dataset = pydicom.dcmread(str(paths[item.index]))
            slope = float(getattr(dataset, "RescaleSlope", 1) or 1)
            intercept = float(getattr(dataset, "RescaleIntercept", 0) or 0)
            planes.append(dataset.pixel_array.astype(np.float32) * slope + intercept)
        report["volume"] = np.stack(planes)
    return report


# Assembled volumes are reused across slice requests: decoding every file per request is slow.
_VOLUME_CACHE: "OrderedDict[tuple, dict[str, Any]]" = OrderedDict()
_VOLUME_CACHE_LOCK = threading.Lock()
VOLUME_CACHE_ENTRIES = 2


def cached_assembly(key: tuple, load: Callable[[], dict[str, Any]]) -> dict[str, Any]:
    """The assembled report with pixels for ``key`` (upload ids and file hashes), from cache when present."""
    with _VOLUME_CACHE_LOCK:
        if key in _VOLUME_CACHE:
            _VOLUME_CACHE.move_to_end(key)
            return _VOLUME_CACHE[key]
    report = load()
    if report.get("status") == "ASSEMBLED":
        with _VOLUME_CACHE_LOCK:
            _VOLUME_CACHE[key] = report
            while len(_VOLUME_CACHE) > VOLUME_CACHE_ENTRIES:
                _VOLUME_CACHE.popitem(last=False)
    return report


PLANES = {"axial": 0, "coronal": 1, "sagittal": 2}


def render_series_slice(report: dict[str, Any], axis: str = "axial", index: Optional[int] = None,
                        center: Optional[float] = None, width: Optional[float] = None) -> tuple[bytes, dict[str, Any]]:
    """One voxel-index plane of an assembled series as PNG: axial = one slice (rows x columns),
    coronal = one row (slices x columns), sagittal = one column (slices x rows), slice 0 at the top."""
    import io

    from PIL import Image

    from app.services.imaging_readers import _window

    volume = report["volume"]
    dim = PLANES[axis]
    count = volume.shape[dim]
    position = count // 2 if index is None else min(max(int(index), 0), count - 1)
    plane = np.take(volume, position, axis=dim)
    image8, low, high, source = _window(plane, center, width)
    buffer = io.BytesIO()
    Image.fromarray(image8).save(buffer, format="PNG")
    spacing = report["spacing_mm"]
    vertical, horizontal = {"axial": (spacing["row"], spacing["column"]), "coronal": (spacing["slice"], spacing["column"]),
                            "sagittal": (spacing["slice"], spacing["row"])}[axis]
    return buffer.getvalue(), {
        "axis": axis, "index": position, "count": count, "shape": list(plane.shape),
        "pixel_spacing_mm": {"vertical": vertical, "horizontal": horizontal},
        "window": {"low": low, "high": high, "source": source},
        "plane": {"axial": "slice k: rows (top to bottom) x columns", "coronal": "row j: slices (top to bottom) x columns",
                  "sagittal": "column i: slices (top to bottom) x rows"}[axis],
    }
