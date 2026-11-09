"""Patient-derived surfaces of a volumetric run, checked on a synthetic phantom (geometry QA only).

The phantom is an ellipsoid label in an anisotropic voxel grid, encoded exactly as stored runs encode
their slices (COCO RLE of mask[:, :, k].T). No clinical data is used."""

import numpy as np
import pytest

pytest.importorskip("skimage")
from pycocotools import mask as coco_mask  # noqa: E402

from app.services import volume_inference  # noqa: E402

SPACING = (1.5, 1.5, 8.0)


def _phantom() -> np.ndarray:
    i, j, k = np.mgrid[0:64, 0:48, 0:12]
    centre = np.array([30.0, 22.0, 6.0])
    radii_mm = np.array([24.0, 18.0, 40.0])
    offsets = (np.stack([i, j, k], axis=-1) - centre) * np.array(SPACING)
    return ((offsets / radii_mm) ** 2).sum(axis=-1) <= 1.0


def _stored_output(mask: np.ndarray) -> dict:
    slices = []
    for k in range(mask.shape[2]):
        plane = np.asfortranarray(mask[:, :, k].T.astype(np.uint8))
        segments = []
        if plane.any():
            rle = coco_mask.encode(plane)
            segments.append({"class_index": 3, "area_px": int(plane.sum()), "rle": {"size": rle["size"], "counts": rle["counts"].decode("ascii")}})
        slices.append({"slice_index": k, "segments": segments})
    voxel_ml = SPACING[0] * SPACING[1] * SPACING[2] / 1000.0
    return {"type": "volume_segmentation", "volume_shape_ijk": list(mask.shape), "voxel_spacing_mm": list(SPACING), "slices": slices,
            "structures": [{"class_index": 3, "structure": "phantom", "voxels": int(mask.sum()), "volume_ml": round(int(mask.sum()) * voxel_ml, 3)}]}


def _enclosed_volume_ml(vertices: np.ndarray, faces: np.ndarray) -> float:
    a, b, c = vertices[faces[:, 0]], vertices[faces[:, 1]], vertices[faces[:, 2]]
    return abs(float(np.einsum("ij,ij->i", a, np.cross(b, c)).sum()) / 6.0) / 1000.0


def test_stored_slices_rebuild_the_exact_voxel_mask():
    mask = _phantom()
    rebuilt = volume_inference.mask_from_output(_stored_output(mask))
    assert rebuilt.shape == mask.shape and np.array_equal(rebuilt == 3, mask)


def test_surfaces_are_in_millimetres_of_the_voxel_frame_and_enclose_the_mask_volume():
    mask = _phantom()
    result = volume_inference.structure_surfaces(_stored_output(mask))
    assert result["frame"] == "VOXEL_GRID_SCALED_MM" and result["registered_to_atlas"] is False
    [surface] = result["surfaces"]
    vertices = np.array(surface["vertices_mm"]).reshape(-1, 3)
    faces = np.array(surface["faces"]).reshape(-1, 3)
    occupied = np.argwhere(mask)
    for axis in range(3):
        low, high = occupied[:, axis].min() * SPACING[axis], occupied[:, axis].max() * SPACING[axis]
        assert vertices[:, axis].min() >= low - SPACING[axis] - 1e-6 and vertices[:, axis].max() <= high + SPACING[axis] + 1e-6
        assert vertices[:, axis].min() <= low + 1e-6 and vertices[:, axis].max() >= high - 1e-6
    voxel_volume = surface["volume_ml"]
    assert abs(_enclosed_volume_ml(vertices, faces) - voxel_volume) / voxel_volume < 0.15, "the surface encloses about the labelled volume"
