"""
Anatomical Registration and L1/L2/L3 Representation Gate for MedTwin.
Implements Equations 11-12, Fig. 4, and Algorithm 1 (Lines 19-22) of the IEEE manuscript.

ANATOMICAL REPRESENTATION LEVELS:
- L1 (Generic): Displays reference anatomical mesh without claiming patient-specific correspondence.
- L2 (Finding-associated): Visualizes finding on an anatomical region ONLY when registration gate passes:
    1. Valid coordinate frames and projection metadata.
    2. Validated rigid transform T_{A <- M} = [R, t].
    3. Non-empty held-out landmark set Q disjoint from fitting set.
    4. Held-out Target Registration Error (TRE) <= tau_TRE.
- L3 (Patient-specific): Reserved for future work requiring volumetric CT/MRI reconstruction.
"""

from typing import Dict, Any, List, Optional, Tuple
import numpy as np

from app.config import TAU_TRE_THRESHOLD_DEFAULT
from app.models.entities import RepresentationLevel


def fit_rigid_transform_arun(
    source_pts: np.ndarray,
    target_pts: np.ndarray
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Computes closed-form least-squares rigid transform (R*, t*) using Arun's SVD method.
    source_pts (M): shape (N, 3)
    target_pts (A): shape (N, 3)
    """
    if len(source_pts) < 3 or len(target_pts) < 3 or len(source_pts) != len(target_pts):
        raise ValueError("At least 3 non-collinear point correspondences are required for 3D rigid registration.")

    centroid_source = np.mean(source_pts, axis=0)
    centroid_target = np.mean(target_pts, axis=0)

    # Shifted coordinates
    p = source_pts - centroid_source
    q = target_pts - centroid_target

    # Covariance matrix H
    H = np.dot(p.T, q)

    # SVD decomposition: H = U S V^T
    U, S, Vt = np.linalg.svd(H)
    R = np.dot(Vt.T, U.T)

    # Reflection check (ensure det(R) == +1 in SO(3))
    if np.linalg.det(R) < 0:
        Vt[2, :] *= -1
        R = np.dot(Vt.T, U.T)

    t = centroid_target - np.dot(R, centroid_source)
    return R, t


def compute_target_registration_error(
    R: np.ndarray,
    t: np.ndarray,
    held_out_source: np.ndarray,
    held_out_target: np.ndarray
) -> Tuple[float, float]:
    """
    Evaluates held-out Target Registration Error (TRE) (Eq. 12a and 12b).
    Returns: (mean_tre_mm, rms_tre_mm)
    """
    if len(held_out_source) == 0:
        raise ValueError("Held-out landmark set Q is empty. Cannot evaluate out-of-sample TRE.")

    transformed_pts = (np.dot(R, held_out_source.T)).T + t
    errors = np.linalg.norm(transformed_pts - held_out_target, axis=1)

    mean_tre = float(np.mean(errors))
    rms_tre = float(np.sqrt(np.mean(errors ** 2)))
    return mean_tre, rms_tre


def evaluate_registration_gate(
    landmarks_source: List[List[float]],
    landmarks_target: List[List[float]],
    tau_tre: float = TAU_TRE_THRESHOLD_DEFAULT,
    held_out_ratio: float = 0.33,
    *,
    requested_region: Optional[str] = None,
    evidence_manifest_id: Optional[str] = None,
    landmarks_are_independently_held_out: bool = False,
) -> Dict[str, Any]:
    """
    Executes the L1/L2 Anatomical Gate (Fig. 4).
    Enforces held-out TRE validation before any finding is drawn on an anatomical region.
    """
    src = np.array(landmarks_source, dtype=float)
    tgt = np.array(landmarks_target, dtype=float)

    # Check 1: Non-empty point sets with sufficient points
    total_pts = len(src)
    if total_pts < 4 or len(tgt) != total_pts:
        return {
            "passed_gate": False,
            "representation_level": RepresentationLevel.L1_GENERIC.value,
            "assigned_region": None,
            "tre_error": None,
            "tre_threshold": tau_tre,
            "held_out_count": 0,
            "transform_matrix": None,
            "mapping_status": "MAPPING_UNSUPPORTED: Insufficient landmark correspondences (< 4 pairs).",
            "explanatory_reason": "Held-out landmark verification requires at least 4 registered anatomical landmarks."
        }

    # Partition into fitting set and held-out evaluation set Q
    num_held_out = max(1, int(round(total_pts * held_out_ratio)))
    fit_src = src[:-num_held_out]
    fit_tgt = tgt[:-num_held_out]
    q_src = src[-num_held_out:]
    q_tgt = tgt[-num_held_out:]

    if len(fit_src) < 3:
        return {
            "passed_gate": False,
            "representation_level": RepresentationLevel.L1_GENERIC.value,
            "assigned_region": None,
            "tre_error": None,
            "tre_threshold": tau_tre,
            "held_out_count": 0,
            "transform_matrix": None,
            "mapping_status": "MAPPING_UNSUPPORTED: Insufficient fitting landmarks.",
            "explanatory_reason": "Fitting set requires at least 3 point correspondences."
        }

    # Fit transform T using Arun's method
    try:
        R, t = fit_rigid_transform_arun(fit_src, fit_tgt)
        mean_tre, rms_tre = compute_target_registration_error(R, t, q_src, q_tgt)
    except Exception as e:
        return {
            "passed_gate": False,
            "representation_level": RepresentationLevel.L1_GENERIC.value,
            "assigned_region": None,
            "tre_error": None,
            "tre_threshold": tau_tre,
            "held_out_count": len(q_src),
            "transform_matrix": None,
            "mapping_status": f"MAPPING_UNSUPPORTED: Transform calculation failed: {str(e)}",
            "explanatory_reason": "Numerical singularity or coplanar degeneracy during registration."
        }

    # Build 4x4 homogeneous transformation matrix
    T_matrix = np.eye(4)
    T_matrix[:3, :3] = R
    T_matrix[:3, 3] = t

    # Gate decision (line 20 of Algorithm 1):
    # Does held-out TRE <= tau_tre?
    registration_quality_passed = mean_tre <= tau_tre
    provenance_gate_passed = bool(
        requested_region
        and evidence_manifest_id
        and landmarks_are_independently_held_out
    )

    if registration_quality_passed and provenance_gate_passed:
        return {
            "passed_gate": True,
            "registration_quality_passed": True,
            "representation_level": RepresentationLevel.L2_FINDING_ASSOCIATED.value,
            "assigned_region": requested_region,
            "tre_error": round(mean_tre, 3),
            "tre_rms": round(rms_tre, 3),
            "tre_threshold": tau_tre,
            "held_out_count": len(q_src),
            "transform_matrix": T_matrix.tolist(),
            "mapping_status": "L2_RESEARCH_GATE_PASSED: Provenance and held-out TRE requirements were supplied.",
            "explanatory_reason": (
                f"Registration quality passed on {len(q_src)} independently declared held-out landmarks "
                f"(TRE = {mean_tre:.2f} mm <= {tau_tre:.2f} mm); evidence manifest "
                f"{evidence_manifest_id} remains subject to research review."
            ),
        }
    if registration_quality_passed:
        return {
            "passed_gate": False,
            "registration_quality_passed": True,
            "representation_level": RepresentationLevel.L1_GENERIC.value,
            "assigned_region": None,
            "tre_error": round(mean_tre, 3),
            "tre_rms": round(rms_tre, 3),
            "tre_threshold": tau_tre,
            "held_out_count": len(q_src),
            "transform_matrix": T_matrix.tolist(),
            "mapping_status": "MAPPING_UNSUPPORTED: TRE mathematics passed but landmark provenance and an explicit anatomical target were not verified.",
            "explanatory_reason": (
                "A low error on caller-supplied coordinates is not patient-specific registration. "
                "L2 requires a reviewed evidence manifest, a declared anatomical target, and "
                "landmarks independently held out from fitting."
            ),
        }
    else:
        return {
            "passed_gate": False,
            "registration_quality_passed": False,
            "representation_level": RepresentationLevel.L1_GENERIC.value,
            "assigned_region": None,
            "tre_error": round(mean_tre, 3),
            "tre_rms": round(rms_tre, 3),
            "tre_threshold": tau_tre,
            "held_out_count": len(q_src),
            "transform_matrix": T_matrix.tolist(),
            "mapping_status": f"MAPPING_UNSUPPORTED: Held-out TRE ({mean_tre:.2f} mm) exceeds threshold ({tau_tre:.2f} mm).",
            "explanatory_reason": "Held-out registration error exceeded accuracy limits. Region label rejected to protect evidence integrity."
        }
