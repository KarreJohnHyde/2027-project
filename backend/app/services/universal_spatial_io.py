"""Explicit frame selection and physically mapped, plane-at-a-time anatomical resampling.

Source arrays use (i,j,k), unlike the canonical PNG reader's internal (z,y,x).
Only an explicitly selected fourth axis is supported; no channel/time semantics are inferred.
"""
from __future__ import annotations

import io
import itertools
from pathlib import Path
from typing import Literal

import numpy as np
from PIL import Image
from scipy.ndimage import map_coordinates

from app.services.imaging_readers import _volume, _window, read_metadata
from app.services.universal_geometry import GeometryRefusal, lps_to_ras, spatial_contract, validate_affine

MAX_TARGET_AXIS = 1024
MAX_TARGET_VOXELS = 32_000_000


def source_metadata(path: Path, frame_index: int | None = None, frame_kind: str | None = None) -> dict:
    metadata = read_metadata(path)
    shape = list(metadata.get("dimensions", []))
    metadata["original_dimensions"] = shape
    selection = {"required": len(shape) == 4, "count": shape[3] if len(shape) == 4 else 1,
                 "axis": 3 if len(shape) == 4 else None, "index": frame_index, "kind": frame_kind,
                 "semantics": "Fourth-axis interpretation is explicitly declared by the viewer; it is not inferred from anatomy or intensities."}
    metadata["frame_selection"] = selection
    if metadata.get("container") == "NIFTI":
        import nibabel as nib
        image = nib.load(str(path))
        metadata["spatial_units"], temporal_units = image.header.get_xyzt_units()
        metadata["affine"] = image.affine.tolist()
        selection["header_temporal_units"] = temporal_units
        selection["header_fourth_axis_spacing"] = float(image.header.get_zooms()[3]) if len(shape) == 4 else None
    if len(shape) == 4:
        if metadata.get("container") != "NIFTI":
            metadata["selection_refusal"] = {"code": "FOURTH_AXIS_FORMAT_UNSUPPORTED", "reason": "Explicit fourth-axis viewing currently supports NIfTI; convert another container with an audited source transform first."}
        elif frame_index is None or frame_kind not in {"channel", "time"}:
            metadata["selection_refusal"] = {"code": "FRAME_SELECTION_REQUIRED", "reason": "Explicitly choose whether the fourth axis is channels or time, then select its zero-based index. No frame is selected automatically."}
        elif not 0 <= frame_index < shape[3]:
            metadata["selection_refusal"] = {"code": "FRAME_OUT_OF_RANGE", "reason": f"The fourth-axis index must be between 0 and {shape[3]-1}."}
        else:
            metadata["dimensions"] = shape[:3]
    elif frame_index is not None or frame_kind is not None:
        metadata["selection_refusal"] = {"code": "UNEXPECTED_FRAME_SELECTION", "reason": "This source has no fourth axis. Clear the frame selection."}
    return metadata


def _ras_affine(contract: dict) -> np.ndarray:
    if not contract.get("world_available"):
        raise GeometryRefusal("PATIENT_WORLD_UNAVAILABLE", "Anatomical resampling and registration require a coded source affine and known physical units. Source-grid viewing remains available.")
    matrix = validate_affine(contract["affine_voxel_to_world"])
    return np.asarray(lps_to_ras(matrix)) if contract["coordinate_frame"] == "LPS_MM" else matrix


def anatomical_grid(contract: dict) -> dict:
    source = _ras_affine(contract)
    dims = contract["dimensions_xyz"]
    corners = np.asarray([source @ [*point, 1.] for point in itertools.product(*[(0, n-1) for n in dims])])[:, :3]
    low, high = corners.min(axis=0), corners.max(axis=0)
    spacing = max(.25, min(np.linalg.norm(source[:3, :3], axis=0)))
    shape = np.ceil((high-low) / spacing).astype(int) + 1
    # Increase isotropic spacing, never truncate the source field of view.
    factor = max(1., float(shape.max()) / MAX_TARGET_AXIS, float(np.prod(shape, dtype=float) / MAX_TARGET_VOXELS) ** (1/3))
    spacing *= factor * (1.001 if factor > 1 else 1.)
    shape = np.ceil((high-low) / spacing).astype(int) + 1
    if shape.max() > MAX_TARGET_AXIS or np.prod(shape, dtype=np.int64) > MAX_TARGET_VOXELS:
        raise GeometryRefusal("ANATOMICAL_GRID_BOUNDS", "Anatomical target grid exceeds the resampling limit.")
    target = np.diag([spacing, spacing, spacing, 1.]); target[:3, 3] = low
    return {"dimensions_xyz": shape.tolist(), "spacing_xyz_mm": [float(spacing)]*3,
            "affine_voxel_to_world": target.tolist(), "coordinate_frame": "RAS_MM",
            "view_to_native_voxel": (np.linalg.inv(source) @ target).tolist(),
            "native_to_view_voxel": (np.linalg.inv(target) @ source).tolist(),
            "downsampled_for_bounds": factor > 1}


def view_contract(metadata: dict, source: dict, view_space: str = "source") -> dict:
    result = spatial_contract(metadata, source)
    result["frame_selection"] = metadata.get("frame_selection")
    result["original_dimensions"] = metadata.get("original_dimensions", metadata.get("dimensions"))
    result["view_space"] = view_space
    result["available_view_spaces"] = ["source"] + (["anatomical"] if result.get("world_available") else [])
    if metadata.get("selection_refusal"):
        result.update(status="REFUSED", refusal=metadata["selection_refusal"])
        result["capabilities"].update(index_mpr=False, source_3d_planes=False)
        return result
    return configure_view(result, view_space)


def configure_view(result: dict, view_space: str = "source") -> dict:
    result["view_space"] = view_space
    result["available_view_spaces"] = ["source"] + (["anatomical"] if result.get("world_available") else [])
    if result["status"] != "AVAILABLE":
        return result
    native = {key: result[key] for key in ["dimensions_xyz", "spacing_xyz_mm", "affine_voxel_to_world", "coordinate_frame", "affine_voxel_to_display", "display_frame"]}
    result["native_geometry"] = native
    result["view_to_native_voxel"] = np.eye(4).tolist()
    result["native_to_view_voxel"] = np.eye(4).tolist()
    if view_space == "anatomical":
        try:
            grid = anatomical_grid(result)
            result.update(grid)
            result["affine_voxel_to_display"] = grid["affine_voxel_to_world"]
            result["display_frame"] = "ANATOMICAL_RAS_MM"
            result["plane_definition"] = "Physically resampled anatomical RAS-mm planes. Image intensities use linear interpolation; categorical masks use nearest-neighbour interpolation. Original native data are preserved."
            result["oblique_or_non_axis_aligned"] = False
            result["non_axial_vertical_flip"] = True
            if grid["downsampled_for_bounds"]:
                result["warnings"].append("Anatomical display spacing was increased to preserve the full field of view within display bounds; this does not increase source resolution.")
        except GeometryRefusal as exc:
            result.update(status="REFUSED", refusal={"code": exc.code, "reason": exc.reason})
            result["capabilities"].update(index_mpr=False, source_3d_planes=False)
    return result


def read_selected_volume(path: Path, metadata: dict) -> np.ndarray:
    if metadata.get("selection_refusal"):
        raise GeometryRefusal(**metadata["selection_refusal"])
    if metadata.get("container") == "NIFTI":
        import nibabel as nib
        image = nib.load(str(path))
        selection = metadata.get("frame_selection") or {}
        data = image.dataobj[..., selection["index"]] if selection.get("required") else image.dataobj
        array = np.asanyarray(data).astype(np.float32)
    else:
        array = np.transpose(_volume(path)[0], (2, 1, 0))
    if array.ndim != 3 or list(array.shape) != metadata["dimensions"]:
        raise GeometryRefusal("SELECTED_GRID_MISMATCH", "Selected frame does not match the declared native spatial grid.")
    return array


def sample_plane(array: np.ndarray, contract: dict, axis: Literal["axial", "coronal", "sagittal"], index: int | None = None, *, categorical: bool = False) -> tuple[np.ndarray, dict]:
    dims = contract["dimensions_xyz"]
    fixed = {"axial": 2, "coronal": 1, "sagittal": 0}[axis]
    index = dims[fixed]//2 if index is None else index
    if not 0 <= index < dims[fixed]:
        raise GeometryRefusal("SLICE_OUT_OF_RANGE", "Requested slice is outside the selected view grid.")
    width, height = {"axial": (dims[0], dims[1]), "coronal": (dims[0], dims[2]), "sagittal": (dims[1], dims[2])}[axis]
    u, v = np.meshgrid(np.arange(width, dtype=float), np.arange(height, dtype=float))
    z = dims[2]-1-v if contract["non_axial_vertical_flip"] and axis != "axial" else v
    coordinates = np.stack({"axial": [u, v, np.full_like(u, index)], "coronal": [u, np.full_like(u, index), z], "sagittal": [np.full_like(u, index), u, z]}[axis])
    transform = np.asarray(contract["view_to_native_voxel"])
    native = np.einsum("ij,jhw->ihw", transform[:3, :3], coordinates) + transform[:3, 3, None, None]
    # Floating-point affine roundoff at a valid source boundary must not create a blank border.
    native[np.abs(native) < 1e-7] = 0
    for i, n in enumerate(array.shape):
        native[i][np.abs(native[i]-(n-1)) < 1e-7] = n-1
    valid = np.all([(native[i] >= 0) & (native[i] <= array.shape[i]-1) for i in range(3)], axis=0)
    plane = map_coordinates(array, native, order=0 if categorical else 1, mode="constant", cval=0 if categorical else np.nan, prefilter=False)
    return plane, {"axis": axis, "slice_index": index, "slice_count": dims[fixed], "display_dimensions": [width, height], "view_space": contract["view_space"], "valid_source_fraction": float(valid.mean()), "interpolation": "NEAREST_NEIGHBOUR" if categorical else "LINEAR", "view_to_native_voxel": contract["view_to_native_voxel"], "frame_selection": contract.get("frame_selection"), "coordinate_frame": contract["coordinate_frame"], "plane_definition": contract["plane_definition"]}


def render_plane(array: np.ndarray, contract: dict, axis: str, index: int | None, center: float | None, width: float | None, *, categorical: bool = False, reviewer: bool = False) -> tuple[bytes, dict]:
    plane, info = sample_plane(array, contract, axis, index, categorical=categorical)
    if categorical:
        rgba = np.zeros((*plane.shape, 4), dtype=np.uint8)
        colors = [(34, 211, 238, 150), (245, 170, 40, 150), (236, 72, 153, 150)]
        for label in np.unique(plane):
            if label > 0:
                rgba[plane == label] = (251, 146, 60, 150) if reviewer else colors[(int(label)-1) % len(colors)]
        image = Image.fromarray(rgba)
    else:
        if np.isfinite(plane).any():
            with np.errstate(invalid="ignore"):
                pixels, low, high, source = _window(plane, center, width)
        else:
            pixels, low, high, source = np.zeros(plane.shape, dtype=np.uint8), 0., 1., "NO_VALID_SOURCE_PIXELS"
        pixels[~np.isfinite(plane)] = 0
        image = Image.fromarray(pixels)
        info["window"] = {"low": low, "high": high, "source": source}
    buffer = io.BytesIO(); image.save(buffer, format="PNG")
    return buffer.getvalue(), info
