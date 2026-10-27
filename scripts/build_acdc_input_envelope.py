"""Record the input envelope of the ACDC cardiac MRI segmenter from NIfTI headers.

The envelope is the range of voxel spacing and matrix size over the development cases
(publisher training set: the train and validation splits of the manifest). Upload
inference refuses frames whose spacing lies outside it. Test cases are only counted, to
report how many held-out cases the gate itself would refuse; they do not shape the range.
Only headers are read; the output holds ranges and counts, no case identifiers.

  .venv\\Scripts\\python.exe scripts/build_acdc_input_envelope.py
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

import nibabel as nib

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "_derived" / "datasets" / "acdc-cardiac-segmentation" / "manifest.json"
OUTPUT = ROOT / "docs" / "validation" / "models" / "acdc_cardiac_mri_3d_unet_input_envelope.json"
sys.path.insert(0, str(ROOT / "backend"))
from app.services.volume_inference import VolumeInputError, read_volume  # noqa: E402


def main() -> int:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    root = Path(manifest["dataset_root"])
    root = root if root.is_absolute() else ROOT / root
    geometry = {}
    for case in manifest["cases"]:
        image = nib.load(str(root / case["image_path"]))
        zooms = [float(value) for value in image.header.get_zooms()[:3]]
        geometry.setdefault(case["split"], []).append({"path": root / case["image_path"], "shape": [int(v) for v in image.shape[:3]],
                                                       "zooms": zooms, "unit_code": int(image.header["xyzt_units"]) & 0x07, "ndim": len(image.shape)})
    development = geometry["train"] + geometry["val"]
    bounds = lambda values: {"min": min(values), "max": max(values)}  # noqa: E731
    envelope = {
        "model_id": "acdc_cardiac_mri_3d_unet",
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": hashlib.sha256(MANIFEST.read_bytes()).hexdigest(),
        "derived_from": "NIfTI headers of the development cases (manifest train and validation splits); test cases do not shape the range",
        "development_cases": len(development),
        "ndim": sorted({item["ndim"] for item in development}),
        "spatial_unit_codes": sorted({item["unit_code"] for item in development}),
        "in_plane_spacing_mm": bounds([item["zooms"][0] for item in development]),
        "in_plane_square_pixels": all(abs(item["zooms"][0] - item["zooms"][1]) <= 1e-3 * item["zooms"][0] for item in development),
        "slice_spacing_mm": bounds([item["zooms"][2] for item in development]),
        "slice_axis_last": all(item["zooms"][2] > max(item["zooms"][:2]) for item in development),
        "matrix": {axis: bounds([item["shape"][index] for item in development]) for index, axis in enumerate(("i", "j", "k"))},
    }
    refused_cases, refused, warned = 0, Counter(), Counter()
    for item in geometry["test"]:
        try:
            result = read_volume(item["path"], envelope)
        except VolumeInputError as exc:
            refused_cases += 1
            refused.update(exc.codes)
            continue
        warned.update(warning.split(" ")[0] for warning in result.warnings)
    envelope["publisher_test_cases"] = {"total": len(geometry["test"]), "accepted_by_gate": len(geometry["test"]) - refused_cases,
                                        "refusal_reasons": dict(refused), "warnings": dict(warned)}
    OUTPUT.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8", newline="\n")
    print(json.dumps(envelope, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
