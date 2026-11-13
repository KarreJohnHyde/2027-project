"""Bounded rigid source-to-source registration candidates, never atlas/clinical activation.

SimpleITK convention: optimizer result maps fixed physical points to moving
physical points. Both directions below are explicitly expressed in RAS millimetres.
"""
from __future__ import annotations

import time
import numpy as np
import SimpleITK as sitk

from app.services.universal_geometry import GeometryRefusal, validate_affine
from app.services.universal_spatial_io import _ras_affine

MAX_REGISTRATION_VOXELS = 32_000_000
MAX_SAMPLED_AXIS = 96
MAX_RUNTIME_SECONDS = 20.


def _image(array: np.ndarray, contract: dict) -> sitk.Image:
    affine = _ras_affine(contract)
    if array.ndim != 3 or list(array.shape) != contract["dimensions_xyz"] or array.size > MAX_REGISTRATION_VOXELS:
        raise GeometryRefusal("REGISTRATION_INPUT_BOUNDS", "Registration accepts matching native 3D arrays with at most 32 million voxels per source.")
    spacing = np.linalg.norm(affine[:3, :3], axis=0)
    direction = affine[:3, :3] / spacing
    if not np.allclose(direction.T @ direction, np.eye(3), atol=1e-5):
        raise GeometryRefusal("SHEARED_REGISTRATION_GRID", "Rigid registration requires orthogonal source directions; sheared metadata require explicit audited regridding first.")
    if not np.isfinite(array).all() or float(array.max()) == float(array.min()):
        raise GeometryRefusal("REGISTRATION_INTENSITIES_INVALID", "Registration requires finite, nonconstant source intensities.")
    image = sitk.GetImageFromArray(np.transpose(array.astype(np.float32, copy=False), (2, 1, 0)))
    image.SetSpacing(spacing.tolist()); image.SetOrigin(affine[:3, 3].tolist()); image.SetDirection(direction.ravel().tolist())
    shrink = [max(1, int(np.ceil(n/MAX_SAMPLED_AXIS))) for n in image.GetSize()]
    if any(n > 1 for n in shrink):
        shrinker = sitk.ShrinkImageFilter(); shrinker.SetNumberOfThreads(2); shrinker.SetNumberOfWorkUnits(2); shrinker.SetShrinkFactors(shrink)
        image = shrinker.Execute(image)
    normalizer = sitk.NormalizeImageFilter(); normalizer.SetNumberOfThreads(2); normalizer.SetNumberOfWorkUnits(2)
    return normalizer.Execute(image)


def transform_matrix(transform: sitk.Transform) -> list[list[float]]:
    origin = np.asarray(transform.TransformPoint((0., 0., 0.)))
    matrix = np.eye(4); matrix[:3, 3] = origin
    matrix[:3, :3] = np.column_stack([np.asarray(transform.TransformPoint(tuple(np.eye(3)[i]))) - origin for i in range(3)])
    return validate_affine(matrix).tolist()


def landmark_tre(matrix_moving_to_fixed: list[list[float]], landmarks: list[dict], *, source: str) -> dict:
    if not landmarks:
        return {"status": "NOT_PROVIDED", "n": 0, "independent_clinical_validation": False}
    if len(landmarks) < 3 or len(landmarks) > 100:
        raise GeometryRefusal("LANDMARK_COUNT_INVALID", "Provide 3–100 paired held-out physical landmarks, or none. Landmarks are not used by the optimizer.")
    fixed = np.asarray([p["fixed_ras_mm"] for p in landmarks], dtype=float)
    moving = np.asarray([p["moving_ras_mm"] for p in landmarks], dtype=float)
    if fixed.shape != (len(landmarks), 3) or not np.isfinite(fixed).all() or not np.isfinite(moving).all():
        raise GeometryRefusal("LANDMARK_COORDINATES_INVALID", "Landmarks must contain finite RAS-mm coordinates.")
    if np.linalg.matrix_rank(fixed-fixed.mean(axis=0)) < 2 or np.linalg.matrix_rank(moving-moving.mean(axis=0)) < 2:
        raise GeometryRefusal("LANDMARK_GEOMETRY_DEGENERATE", "Landmarks must include at least three noncollinear locations.")
    matrix = validate_affine(matrix_moving_to_fixed)
    after = moving @ matrix[:3, :3].T + matrix[:3, 3]
    before_mm = np.linalg.norm(fixed-moving, axis=1)
    after_mm = np.linalg.norm(fixed-after, axis=1)
    return {"status": "MEASURED_ENGINEERING_TRE", "n": len(landmarks), "landmark_source": source,
            "used_for_optimization": False, "independent_clinical_validation": False,
            "before_mm": before_mm.tolist(), "after_mm": after_mm.tolist(),
            "before_mean_mm": float(before_mm.mean()), "after_mean_mm": float(after_mm.mean()),
            "after_max_mm": float(after_mm.max()), "after_p95_mm": float(np.percentile(after_mm, 95)),
            "semantics": "TRE on the supplied correspondences only. A low error here does not establish clinical accuracy, disease localization or independent annotator agreement."}


def register_rigid(fixed_array: np.ndarray, fixed_contract: dict, moving_array: np.ndarray, moving_contract: dict,
                   *, landmarks: list[dict] | None = None, landmark_source: str = "REVIEWER_SUPPLIED_UNVERIFIED",
                   metric: str = "mattes") -> dict:
    # Validate landmarks before paying the optimization cost; they do not initialize the transform.
    landmark_tre(np.eye(4).tolist(), landmarks or [], source=landmark_source)
    for contract, key in [(fixed_contract, "fixed_ras_mm"), (moving_contract, "moving_ras_mm")]:
        inverse = np.linalg.inv(_ras_affine(contract))
        for landmark in landmarks or []:
            point = (inverse @ [*landmark[key], 1.])[:3]
            if (point < -1e-5).any() or (point > np.asarray(contract["dimensions_xyz"])-1+1e-5).any():
                raise GeometryRefusal("LANDMARK_OUTSIDE_SOURCE", "Every supplied landmark must lie inside its corresponding source field of view.")
    fixed, moving = _image(fixed_array, fixed_contract), _image(moving_array, moving_contract)
    method = sitk.ImageRegistrationMethod(); method.SetNumberOfThreads(2); method.SetNumberOfWorkUnits(2)
    if metric == "mean_squares":
        method.SetMetricAsMeanSquares()
    elif metric == "mattes":
        method.SetMetricAsMattesMutualInformation(numberOfHistogramBins=32)
    else:
        raise GeometryRefusal("REGISTRATION_METRIC_UNSUPPORTED", "Choose mattes or mean_squares.")
    method.SetMetricSamplingStrategy(method.REGULAR)
    method.SetMetricSamplingPercentage(.3, 20261113)
    method.SetInterpolator(sitk.sitkLinear)
    initial = sitk.CenteredTransformInitializer(fixed, moving, sitk.Euler3DTransform(), sitk.CenteredTransformInitializerFilter.GEOMETRY)
    method.SetInitialTransform(initial, inPlace=False)
    method.SetOptimizerAsRegularStepGradientDescent(learningRate=1., minStep=.0005, numberOfIterations=120, relaxationFactor=.5, gradientMagnitudeTolerance=1e-7)
    method.SetOptimizerScalesFromPhysicalShift()
    method.SetShrinkFactorsPerLevel([2, 1]); method.SetSmoothingSigmasPerLevel([1., 0.])
    method.SmoothingSigmasAreSpecifiedInPhysicalUnitsOn()
    start = time.monotonic(); budget_hit = [False]
    def bound_runtime():
        if time.monotonic()-start > MAX_RUNTIME_SECONDS:
            budget_hit[0] = True; method.StopRegistration()
    method.AddCommand(sitk.sitkIterationEvent, bound_runtime)
    try:
        initial_metric = float(method.MetricEvaluate(fixed, moving))
        transform = method.Execute(fixed, moving)
    except RuntimeError as exc:
        raise GeometryRefusal("REGISTRATION_OPTIMIZATION_REFUSED", "The sources did not support a stable bounded rigid optimization (for example, insufficient overlap).") from exc
    if budget_hit[0]:
        raise GeometryRefusal("REGISTRATION_RUNTIME_BUDGET", "Registration reached its 20-second optimization budget; no accepted transform is returned.")
    fixed_to_moving = transform_matrix(transform)
    moving_to_fixed = np.linalg.inv(fixed_to_moving).tolist()
    optimizer_metric = float(method.GetMetricValue())
    method.SetInitialTransform(transform, inPlace=False)
    final_metric = float(method.MetricEvaluate(fixed, moving))
    if not np.isfinite([initial_metric, final_metric]).all():
        raise GeometryRefusal("REGISTRATION_NONFINITE_RESULT", "Optimizer did not return a finite similarity value.")
    evaluation = landmark_tre(moving_to_fixed, landmarks or [], source=landmark_source)
    return {"schema_version": "medtwin.rigid-registration.v1", "status": "CANDIDATE_UNVALIDATED",
            "transform_type": "RIGID_6_DOF", "coordinate_frame": "RAS_MM",
            "fixed_to_moving_ras_mm": fixed_to_moving, "moving_to_fixed_ras_mm": moving_to_fixed,
            "transform_direction": "fixed_to_moving maps fixed output physical points to moving source physical points; inverse is explicitly supplied.",
            "metric": metric, "initial_metric": initial_metric, "final_metric": final_metric,
            "metric_evaluation": "Initial/final metric evaluated on the same full bounded sampled grids; optimizer uses seeded regular 30% sampling.", "optimizer_metric": optimizer_metric,
            "optimizer_stop": method.GetOptimizerStopConditionDescription(), "elapsed_seconds": round(time.monotonic()-start, 4),
            "sampled_dimensions": {"fixed": list(fixed.GetSize()), "moving": list(moving.GetSize())},
            "landmark_evaluation": evaluation, "atlas_registration": False, "clinical_activation": False,
            "semantics": "Unapproved source-to-source research registration candidate. Similarity optimization is not a validation metric. No atlas transform, clinical action, prediction or original source is changed."}
