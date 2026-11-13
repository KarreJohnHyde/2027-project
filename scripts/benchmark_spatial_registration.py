"""Original synthetic physical-grid benchmark; no third-party or patient dataset.

Known transforms generate the moving image. Held-out point coordinates are used
only after optimization, so image similarity is never substituted for TRE.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import SimpleITK as sitk

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from app.services.universal_geometry import spatial_contract
from app.services.universal_registration import register_rigid


def synthetic_case(angle, shift, source_rotation=0.):
    shape = (56, 60, 48)
    c, s = np.cos(source_rotation), np.sin(source_rotation)
    affine = np.array([[c, -s, 0, -40], [s, c, 0, -45], [0, 0, 1, -35], [0, 0, 0, 1.]]) @ np.diag([1.3, 1.6, 2.1, 1])
    indices = np.indices(shape).reshape(3, -1)
    world = affine[:3, :3] @ indices + affine[:3, 3, None]
    centre = (affine @ [*(np.asarray(shape)-1)/2, 1])[:3]
    centres = [centre+[-17, -18, -16], centre+[15, 13, 10], centre+[-10, 18, 24], centre+[18, -14, 22]]
    values = np.zeros(world.shape[1])
    for number, point in enumerate(centres):
        sigma = np.array([5+number, 7-number*.3, 6+number*.7])
        values += (1+number*.37) * np.exp(-.5*np.sum(((world-point[:, None])/sigma[:, None])**2, axis=0))
    fixed = values.reshape(shape).astype(np.float32)
    image = sitk.GetImageFromArray(fixed.transpose(2, 1, 0))
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    image.SetSpacing(spacing.tolist()); image.SetOrigin(affine[:3, 3].tolist()); image.SetDirection((affine[:3, :3]/spacing).ravel().tolist())
    c, s = np.cos(angle), np.sin(angle)
    rotation = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.]])
    known = np.eye(4); known[:3, :3] = rotation; known[:3, 3] = centre-rotation@centre+shift
    transform = sitk.AffineTransform(3); transform.SetMatrix(rotation.ravel().tolist()); transform.SetTranslation(known[:3, 3].tolist())
    moving = sitk.GetArrayFromImage(sitk.Resample(image, image, transform, sitk.sitkLinear, 0.)).transpose(2, 1, 0)
    landmarks = [{"moving_ras_mm": point.tolist(), "fixed_ras_mm": (rotation@point+known[:3, 3]).tolist()} for point in centres]
    metadata = {"container": "NIFTI", "dimensions": list(shape), "spacing_mm": spacing.tolist(), "affine": affine.tolist(), "qform_code": 1, "sform_code": 1, "spatial_units": "mm"}
    contract = spatial_contract(metadata, {"kind": "ORIGINAL_SYNTHETIC_CONTROL"})
    return fixed, moving, contract, landmarks, known


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/completion-2026-11-13/imaging/registration-benchmark.json")
    args = parser.parse_args()
    output = {"schema_version": "medtwin.synthetic-registration-benchmark.v1", "data_source": "ORIGINAL_PROGRAMMATIC_SYNTHETIC_FIXTURES_NO_THIRD_PARTY_DATA", "independent_clinical_validation": False,
              "source_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "SimpleITK_version": sitk.Version_VersionString(), "success_rule": "Each fixed held-out set has mean TRE <=1.0 mm and max TRE <=2.0 mm; synthetic engineering only.", "cases": []}
    output["implementation_sha256"] = {name: hashlib.sha256((ROOT / "backend/app/services" / name).read_bytes()).hexdigest() for name in ["universal_geometry.py", "universal_spatial_io.py", "universal_registration.py"]}
    output["resource_bounds"] = {"optimizer_threads": 2, "optimizer_work_units": 2, "max_sampled_axis": 96, "max_input_voxels_per_source": 32000000, "optimization_budget_seconds": 20}
    for name, angle, shift, source_rotation in [("anisotropic_translation", 0., [3., -2., 1.], 0.), ("anisotropic_rigid_rotation", .06, [2., -1.5, 1.], 0.), ("oblique_source_grid", -.045, [-2., 1., 1.5], .25)]:
        fixed, moving, contract, landmarks, known = synthetic_case(angle, np.asarray(shift), source_rotation)
        result = register_rigid(fixed, contract, moving, contract, landmarks=landmarks, landmark_source="SYNTHETIC_KNOWN_TRANSFORM", metric="mean_squares")
        evaluation = result["landmark_evaluation"]
        output["cases"].append({"name": name, "native_dimensions": list(fixed.shape), "known_moving_to_fixed_ras_mm": known.tolist(), "landmarks": landmarks, "registration": result,
                                "engineering_threshold_passed": evaluation["after_mean_mm"] <= 1 and evaluation["after_max_mm"] <= 2})
    output["all_engineering_thresholds_passed"] = all(case["engineering_threshold_passed"] for case in output["cases"])
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2), encoding="utf-8")
    print(json.dumps({"artifact": str(args.output), "synthetic_only": True, "passed": output["all_engineering_thresholds_passed"], "cases": [{"name": case["name"], "mean_TRE_mm": case["registration"]["landmark_evaluation"]["after_mean_mm"], "max_TRE_mm": case["registration"]["landmark_evaluation"]["after_max_mm"], "seconds": case["registration"]["elapsed_seconds"]} for case in output["cases"]]}))
    return 0 if output["all_engineering_thresholds_passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
