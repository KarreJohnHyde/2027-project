"""Bounded spatial contracts. Coordinates never imply an atlas registration or diagnosis."""
from __future__ import annotations

from typing import Any
import numpy as np


class GeometryRefusal(ValueError):
    def __init__(self, code: str, reason: str):
        self.code, self.reason = code, reason
        super().__init__(reason)


def validate_affine(value: Any) -> np.ndarray:
    try:
        matrix = np.asarray(value, dtype=float)
    except (ValueError, TypeError) as exc:
        raise GeometryRefusal("MALFORMED_GEOMETRY", "Affine must contain finite numbers.") from exc
    if matrix.shape != (4, 4) or not np.isfinite(matrix).all() or not np.allclose(matrix[3], [0, 0, 0, 1], atol=1e-10):
        raise GeometryRefusal("MALFORMED_GEOMETRY", "Expected a finite homogeneous 4 by 4 affine.")
    if np.linalg.matrix_rank(matrix[:3, :3]) < 3 or np.linalg.cond(matrix[:3, :3]) > 1e10:
        raise GeometryRefusal("NONINVERTIBLE_GEOMETRY", "Affine is singular or too poorly conditioned for coordinate linking.")
    return matrix


def transform_point(affine: Any, xyz: Any, *, inverse: bool = False) -> list[float]:
    matrix = validate_affine(affine)
    point = np.asarray(xyz, dtype=float)
    if point.shape != (3,) or not np.isfinite(point).all():
        raise GeometryRefusal("MALFORMED_COORDINATE", "Coordinates must be three finite numbers.")
    if inverse:
        matrix = np.linalg.inv(matrix)
    return (matrix @ np.append(point, 1))[:3].tolist()


def lps_to_ras(affine: Any) -> list[list[float]]:
    return (np.diag([-1., -1., 1., 1.]) @ validate_affine(affine)).tolist()


def _dimensions(value: Any) -> list[int]:
    if not isinstance(value, (list, tuple)) or len(value) != 3:
        raise GeometryRefusal("EXPLICIT_3D_VOLUME_REQUIRED", "Select a native 3D volume or assemble a validated DICOM series. Raster, single-slice and 4D inputs are not reconstructed into a volume.")
    if any(isinstance(n, bool) or not isinstance(n, (int, np.integer)) or n <= 0 or n > 4096 for n in value) or int(np.prod(value, dtype=np.int64)) > 134217728:
        raise GeometryRefusal("VOLUME_BOUNDS_EXCEEDED", "Volume dimensions exceed the spatial viewer's bounded input limit.")
    if any(n < 2 for n in value):
        raise GeometryRefusal("SPATIAL_DEPTH_UNAVAILABLE", "Each displayed volume axis must contain at least two source voxels. A single plane cannot establish a 3D volume.")
    return [int(n) for n in value]


def spatial_contract(metadata: dict, source: dict, *, series: bool = False) -> dict:
    """Patient world is available only for an explicitly coded, physically scaled source."""
    base = {
        "schema_version": "medtwin.spatial.v1", "source": source,
        "status": "REFUSED", "refusal": None, "dimensions_xyz": None,
        "spacing_xyz_mm": None, "affine_voxel_to_world": None,
        "coordinate_frame": None, "world_available": False,
        "world_refusal": {"code": "PATIENT_WORLD_UNAVAILABLE", "reason": "A coded, invertible source transform with known spatial units is required."},
        "affine_voxel_to_display": None, "display_frame": "VOXEL_INDEX",
        "plane_definition": "Orthogonal voxel-index planes; no resampling to patient-anatomical planes. Oblique source directions remain oblique.",
        "plane_mapping": {"axial": "(u,v,k)", "coronal": "(u,j,nz-1-v)", "sagittal": "(i,u,nz-1-v)"},
        "non_axial_vertical_flip": not series,
        "registration": {"status": "REGISTRATION_UNAVAILABLE", "atlas_transform": None, "semantics": "No patient-to-atlas transform exists. L1 anatomical context and source-space coordinates are separate."},
        "capabilities": {"index_mpr": False, "source_3d_planes": False, "patient_world": False, "atlas_overlay": False, "segmentation": "STORED_RUN_REQUIRED"},
        "warnings": [],
        "geometry_provenance": {"container": "DICOM_SERIES" if series else metadata.get("container"), "spatial_units": "mm" if series else metadata.get("spatial_units"), "qform_code": metadata.get("qform_code"), "sform_code": metadata.get("sform_code"), "semantics": "Source-header coordinates; no independent patient registration has been performed."},
    }
    if series:
        base["plane_mapping"] = {"axial": "(u,v,k)", "coronal": "(u,j,v)", "sagittal": "(i,u,v)"}
    try:
        if series:
            if metadata.get("status") != "ASSEMBLED":
                raise GeometryRefusal("DICOM_SERIES_NOT_ASSEMBLED", "Series geometry was rejected or requires explicit series/phase selection.")
            z, y, x = metadata["shape_slices_rows_columns"]
            dims = _dimensions([x, y, z])
            matrix = validate_affine(metadata.get("affine_lps_mm"))
            frame, units = "LPS_MM", "mm"
            spacing = np.linalg.norm(matrix[:3, :3], axis=0)
        else:
            if metadata.get("container") not in {"NIFTI", "NRRD", "METAIMAGE"}:
                raise GeometryRefusal("NATIVE_VOLUME_REQUIRED", "This source supports a 2D preview only. A photograph or raster cannot establish depth, patient orientation or a native 3D surface.")
            dims = _dimensions(metadata.get("dimensions"))
            spacing = np.asarray(metadata.get("spacing_mm"), dtype=float)
            if spacing.shape != (3,) or not np.isfinite(spacing).all() or (spacing <= 0).any():
                raise GeometryRefusal("MALFORMED_SPACING", "Three positive, finite source spacings are required.")
            if metadata.get("container") == "NIFTI":
                # Nibabel's fallback affine is numerical; it is not a coded patient-world transform.
                coded = metadata.get("qform_code", 0) > 0 or metadata.get("sform_code", 0) > 0
                matrix = validate_affine(metadata.get("affine"))
                units = metadata.get("spatial_units", "unknown")
                scale = {"mm": 1., "meter": 1000., "micron": .001}.get(units)
                frame = "RAS_MM" if coded and scale is not None else None
                if scale is not None:
                    matrix[:3, :] *= scale
                    spacing = spacing * scale
                if not coded:
                    base["warnings"].append("NIfTI qform/sform codes are zero: patient orientation and origin are unverified. Display uses a spacing-only source grid.")
                if scale is None:
                    base["warnings"].append("NIfTI spatial units are unspecified: no millimetre or patient-world claim is made.")
            else:
                direction = np.asarray(metadata.get("direction"), dtype=float)
                origin = np.asarray(metadata.get("origin_mm"), dtype=float)
                if direction.size != 9 or origin.shape != (3,) or not np.isfinite(origin).all():
                    raise GeometryRefusal("MALFORMED_GEOMETRY", "ITK origin and 3D direction matrix are required.")
                matrix = np.eye(4)
                matrix[:3, :3] = direction.reshape(3, 3) @ np.diag(spacing)
                matrix[:3, 3] = origin
                matrix = validate_affine(matrix)
                frame, units = "LPS_MM", "mm"
        world = frame is not None
        if world:
            affine_spacing = np.linalg.norm(matrix[:3, :3], axis=0)
            if not np.allclose(affine_spacing, spacing, rtol=1e-5, atol=1e-6):
                base["warnings"].append("Header spacings differ from the selected affine; spatial display uses affine column lengths. Stored mask spacing must match before an overlay is offered.")
            spacing = affine_spacing
        display = matrix if world else np.diag([*spacing, 1.])
        base.update(status="AVAILABLE", dimensions_xyz=dims,
                    spacing_xyz_mm=spacing.tolist() if units in {"mm", "meter", "micron"} else None,
                    affine_voxel_to_world=matrix.tolist() if world else None,
                    coordinate_frame=frame, world_available=world,
                    affine_voxel_to_display=display.tolist(),
                    display_frame=frame if world else ("SOURCE_GRID_MM" if units in {"mm", "meter", "micron"} else "SOURCE_GRID_UNSPECIFIED_UNITS"))
        base["capabilities"].update(index_mpr=True, source_3d_planes=True, patient_world=world)
        if world:
            base["world_refusal"] = None
        if world:
            directions = matrix[:3, :3] / np.linalg.norm(matrix[:3, :3], axis=0)
            base["oblique_or_non_axis_aligned"] = not bool(np.allclose(np.sort(np.abs(directions), axis=0), [[0]*3, [0]*3, [1]*3], atol=1e-5))
        else:
            base["oblique_or_non_axis_aligned"] = None
    except (GeometryRefusal, ValueError, TypeError, KeyError) as exc:
        refusal = exc if isinstance(exc, GeometryRefusal) else GeometryRefusal("MALFORMED_GEOMETRY", "Source spatial metadata are incomplete or malformed.")
        base["refusal"] = {"code": refusal.code, "reason": refusal.reason}
    return base
