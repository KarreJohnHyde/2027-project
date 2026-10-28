"""
3D Anatomical Assets and Registration Gate Router for MedTwin.
Enforces the L1/L2/L3 representation taxonomy:
- L1 (Generic Reference Mesh): Default state.
- L2 (Finding-Associated): Gated by held-out Target Registration Error (TRE <= tau_TRE).
- L3 (Patient-Specific): Strictly prohibited unless full 3D volumetric reconstruction is validated.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import List, Literal, Optional

import numpy as np
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Finding, AnatomicalAsset, AnatomicalMapping, LandmarkManifest, RepresentationLevel, User, UserRole
from app.schemas.entities import AnatomicalAssetResponse, RegistrationGateCheck, RegistrationResponse
from app.services.auth import get_current_user, require_role, verify_case_access
from app.services.registration_service import evaluate_registration_gate
from app.services.audit_service import log_audit_event
from app.services.anatomy_registry import REFERENCE_ASSETS

router = APIRouter(tags=["3D Anatomy & Registration"])


@router.get("/assets/anatomy", response_model=List[AnatomicalAssetResponse])
def list_anatomical_assets(db: Session = Depends(get_db)):
    """
    Returns available Blender-prepared .glb assets.
    Explicitly tags generic meshes as L1 (never patient-specific).
    """
    # Keep isolated/test databases aligned with the canonical attributed set.
    changed = False
    for definition in REFERENCE_ASSETS:
        if db.query(AnatomicalAsset).filter(
            AnatomicalAsset.asset_path == definition["asset_path"]
        ).first():
            continue
        db.add(
            AnatomicalAsset(
                **definition,
                format="glb",
                representation_level=RepresentationLevel.L1_GENERIC,
                is_available=True,
            )
        )
        changed = True
    if changed:
        db.commit()
    return db.query(AnatomicalAsset).order_by(AnatomicalAsset.id.asc()).all()


@router.post("/findings/{finding_id}/registration-gate", response_model=RegistrationResponse)
def execute_registration_gate(
    finding_id: int,
    gate_req: RegistrationGateCheck,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Applies the Arun least-squares rigid registration algorithm and tests held-out TRE against tau_TRE.
    If valid and TRE <= threshold -> Grants L2 level and anatomical region label.
    Otherwise -> Reverts to L1 Generic, region is set to NULL, and logs an explicit explanatory status.
    """
    finding = db.query(Finding).filter(Finding.id == finding_id).first()
    if not finding:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")

    verify_case_access(finding.case_id, current_user, db)
    if gate_req.finding_id != finding_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The path and payload finding IDs must match.",
        )

    manifest = None
    if gate_req.manifest_id is not None:
        manifest = db.get(LandmarkManifest, gate_req.manifest_id)
        if manifest is None or manifest.finding_id != finding_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Landmark manifest not found for this finding.")
        if manifest.status != "APPROVED":
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Landmark manifest is {manifest.status}; only an approved manifest can be used.")
        pairs = manifest.fit_landmarks + manifest.held_out_landmarks
        gate_req.landmarks_source = [pair["source"] for pair in pairs]
        gate_req.landmarks_target = [pair["target"] for pair in pairs]
        gate_req.coordinate_frame = manifest.coordinate_frame
        gate_req.threshold_mm = manifest.threshold_mm
    source_pts = gate_req.landmarks_source
    target_pts = gate_req.landmarks_target
    if len(source_pts) < 4 or len(target_pts) < 4 or len(source_pts) != len(target_pts):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "MAPPING_UNSUPPORTED: Provide at least four matched source and target landmarks. "
                "MedTwin does not substitute canned landmarks for case evidence."
            ),
        )

    threshold = gate_req.threshold_mm if gate_req.threshold_mm is not None else 5.0
    # The public request does not accept a self-asserted evidence-verification flag: raw
    # coordinates exercise TRE mathematics but never promote a finding beyond L1. Only an
    # approved landmark manifest (proposed and approved by two verified clinicians) can.
    if manifest is not None:
        gate_result = evaluate_registration_gate(
            source_pts, target_pts, tau_tre=threshold, requested_region=manifest.requested_region,
            evidence_manifest_id=f"landmark-manifest-{manifest.id}", landmarks_are_independently_held_out=True,
            held_out_count=len(manifest.held_out_landmarks),
        )
    else:
        gate_result = evaluate_registration_gate(source_pts, target_pts, tau_tre=threshold)

    # Update finding
    if gate_result["passed_gate"]:
        finding.representation_level = RepresentationLevel.L2_FINDING_ASSOCIATED
        finding.anatomical_region = gate_result["assigned_region"]
        finding.mapping_status = gate_result["mapping_status"]
    else:
        finding.representation_level = RepresentationLevel.L1_GENERIC
        finding.anatomical_region = None
        finding.mapping_status = gate_result["mapping_status"]

    finding.tre_score = gate_result["tre_error"]
    finding.tre_threshold = gate_result["tre_threshold"]

    # Store or update AnatomicalMapping record
    existing_mapping = db.query(AnatomicalMapping).filter(AnatomicalMapping.finding_id == finding.id).first()
    if existing_mapping:
        db.delete(existing_mapping)
        db.flush()  # the replacement has the same unique finding_id; delete first

    mapping_record = AnatomicalMapping(
        finding_id=finding.id,
        coordinate_frame=gate_req.coordinate_frame,
        projection_metadata_valid=True,
        transform_matrix=gate_result["transform_matrix"],
        held_out_landmarks_count=gate_result["held_out_count"],
        tre_error=gate_result["tre_error"],
        tre_threshold=gate_result["tre_threshold"],
        passed_gate=gate_result["passed_gate"],
        assigned_region=gate_result["assigned_region"],
        mapping_status=gate_result["mapping_status"]
    )
    db.add(mapping_record)
    db.commit()
    db.refresh(finding)

    log_audit_event(
        db=db,
        action="REGISTRATION_GATE_EVALUATED",
        resource_type="FINDING",
        resource_id=str(finding.id),
        user=current_user,
        details={
            "finding_id": finding.id,
            "passed": gate_result["passed_gate"],
            "tre_error": gate_result["tre_error"],
            "threshold": threshold,
            "level": finding.representation_level.value
        }
    )

    return {
        "finding_id": finding.id,
        "coordinate_frame": gate_req.coordinate_frame,
        "transform_matrix": gate_result["transform_matrix"],
        "held_out_landmarks_count": gate_result["held_out_count"],
        "tre_error": gate_result["tre_error"],
        "tre_threshold": gate_result["tre_threshold"],
        "passed_gate": gate_result["passed_gate"],
        "representation_level": finding.representation_level,
        "assigned_region": finding.anatomical_region,
        "mapping_status": finding.mapping_status,
        "explanatory_reason": gate_result["explanatory_reason"]
    }


class LandmarkPair(BaseModel):
    source: List[float] = Field(..., min_length=3, max_length=3)
    target: List[float] = Field(..., min_length=3, max_length=3)


class LandmarkManifestCreate(BaseModel):
    coordinate_frame: str = Field(..., min_length=3, max_length=128)
    requested_region: str = Field(..., min_length=2, max_length=128)
    fit_pairs: List[LandmarkPair] = Field(..., min_length=3, max_length=200)
    held_out_pairs: List[LandmarkPair] = Field(..., min_length=1, max_length=100)
    threshold_mm: float = Field(5.0, gt=0, le=50)

    model_config = ConfigDict(extra="forbid")


class LandmarkManifestDecision(BaseModel):
    decision: Literal["APPROVED", "REJECTED"]
    comment: Optional[str] = Field(default=None, max_length=2000)

    model_config = ConfigDict(extra="forbid")


def _serialize_manifest(manifest: LandmarkManifest) -> dict:
    return {
        "id": manifest.id, "finding_id": manifest.finding_id, "case_id": manifest.case_id, "coordinate_frame": manifest.coordinate_frame,
        "requested_region": manifest.requested_region, "fit_pairs": len(manifest.fit_landmarks), "held_out_pairs": len(manifest.held_out_landmarks),
        "threshold_mm": manifest.threshold_mm, "status": manifest.status, "created_by_id": manifest.created_by_id,
        "created_at": manifest.created_at.isoformat(), "decided_by_id": manifest.decided_by_id,
        "decided_at": manifest.decided_at.isoformat() if manifest.decided_at else None, "decision_comment": manifest.decision_comment,
    }


@router.post("/findings/{finding_id}/landmark-manifests", status_code=status.HTTP_201_CREATED)
def propose_landmark_manifest(
    finding_id: int,
    payload: LandmarkManifestCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN)),
):
    """Propose landmark correspondences for a finding's registration. Held-out landmarks are declared
    now and are never used for fitting; another verified clinician must approve the manifest."""
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    verify_case_access(finding.case_id, current_user, db)
    fit_source = np.array([pair.source for pair in payload.fit_pairs], dtype=float)
    fit_target = np.array([pair.target for pair in payload.fit_pairs], dtype=float)
    every = np.vstack([fit_source, fit_target] + [np.array([[*pair.source, *pair.target] for pair in payload.held_out_pairs]).reshape(-1, 3)])
    if not np.all(np.isfinite(every)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Landmark coordinates must be finite numbers.")
    for points, side in ((fit_source, "source"), (fit_target, "target")):
        if np.linalg.matrix_rank(points - points.mean(axis=0), tol=1e-6) < 2:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=f"The fitting {side} landmarks are collinear; a rigid transform is undetermined.")
    fitted = {(tuple(pair.source), tuple(pair.target)) for pair in payload.fit_pairs}
    if any((tuple(pair.source), tuple(pair.target)) in fitted for pair in payload.held_out_pairs):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Held-out landmarks must not repeat fitting landmarks.")
    manifest = LandmarkManifest(
        case_id=finding.case_id, finding_id=finding.id, coordinate_frame=payload.coordinate_frame, requested_region=payload.requested_region,
        fit_landmarks=[pair.model_dump() for pair in payload.fit_pairs], held_out_landmarks=[pair.model_dump() for pair in payload.held_out_pairs],
        threshold_mm=payload.threshold_mm, status="PROPOSED", created_by_id=current_user.id,
    )
    db.add(manifest)
    db.commit()
    db.refresh(manifest)
    log_audit_event(db=db, action="LANDMARK_MANIFEST_PROPOSED", resource_type="FINDING", resource_id=str(finding.id), user=current_user,
                    details={"manifest_id": manifest.id, "fit_pairs": len(payload.fit_pairs), "held_out_pairs": len(payload.held_out_pairs)})
    return _serialize_manifest(manifest)


@router.get("/findings/{finding_id}/landmark-manifests")
def list_landmark_manifests(finding_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    finding = db.get(Finding, finding_id)
    if finding is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Finding not found.")
    verify_case_access(finding.case_id, current_user, db, access="read")
    rows = db.query(LandmarkManifest).filter(LandmarkManifest.finding_id == finding_id).order_by(LandmarkManifest.id.asc()).all()
    return [_serialize_manifest(manifest) for manifest in rows]


@router.post("/landmark-manifests/{manifest_id}/decision")
def decide_landmark_manifest(
    manifest_id: int,
    payload: LandmarkManifestDecision,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role(UserRole.CLINICIAN, UserRole.ADMIN)),
):
    """Approve or reject a proposed manifest; the proposer cannot decide their own manifest."""
    manifest = db.get(LandmarkManifest, manifest_id)
    if manifest is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Landmark manifest not found.")
    verify_case_access(manifest.case_id, current_user, db)
    if manifest.created_by_id == current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="A second, independent clinician must decide this manifest.")
    if manifest.status != "PROPOSED":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Manifest already {manifest.status}.")
    manifest.status = payload.decision
    manifest.decided_by_id = current_user.id
    manifest.decided_at = datetime.now(timezone.utc)
    manifest.decision_comment = payload.comment
    db.commit()
    db.refresh(manifest)
    log_audit_event(db=db, action=f"LANDMARK_MANIFEST_{payload.decision}", resource_type="FINDING", resource_id=str(manifest.finding_id),
                    user=current_user, details={"manifest_id": manifest.id})
    return _serialize_manifest(manifest)


class EvaluateRegistrationRequest(BaseModel):
    case_id: Optional[int] = None
    finding_category: Optional[str] = "FRACTURE"
    tau_tre_threshold: Optional[float] = 5.0
    simulate_high_error: Optional[bool] = False


@router.post("/anatomy/evaluate-registration")
def evaluate_registration_for_case(
    req: EvaluateRegistrationRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Exercises registration-gate mathematics on an explicit synthetic fixture.

    This endpoint never updates a case or finding and cannot establish L2 patient
    mapping. Real mapping requires /findings/{id}/registration-gate with supplied
    provenance-backed landmarks.
    """
    # A caller-provided case ID is allowed only as an audit association after
    # the same ownership check used by all case-scoped resources. This prevents
    # one user from injecting synthetic audit events into another user's case.
    if req.case_id is not None:
        verify_case_access(req.case_id, current_user, db)

    # Reference anatomical landmark correspondences (Radial styloid, Ulnar styloid, Lister's tubercle, Scaphoid fossa, Lunate fossa)
    source_pts = [
        [12.4, 45.1, 8.2],
        [-10.2, 43.8, 6.1],
        [1.5, 48.0, 11.3],
        [8.1, 41.2, 7.0],
        [-4.5, 39.0, 5.5]
    ]
    target_pts = [
        [13.1, 46.0, 8.5],
        [-9.8, 44.5, 6.4],
        [2.1, 49.2, 11.8],
        [8.8, 42.0, 7.3],
        [-4.0, 39.8, 5.8]
    ]
    if req.simulate_high_error:
        # Severe perturbation to demonstrate gate failure and fallback to L1 Generic
        target_pts = [
            [28.0, 62.0, 22.0],
            [-25.0, 58.0, 19.0],
            [15.0, 65.0, 25.0],
            [22.0, 55.0, 20.0],
            [-18.0, 52.0, 18.0]
        ]

    threshold = req.tau_tre_threshold if req.tau_tre_threshold is not None else 5.0
    gate_result = evaluate_registration_gate(source_pts, target_pts, tau_tre=threshold)

    is_passed = gate_result["passed_gate"]
    quality_passed = gate_result.get("registration_quality_passed", False)
    tre_val = gate_result["tre_error"]

    log_audit_event(
        db=db,
        action="REGISTRATION_GATE_EVALUATED",
        resource_type="ANATOMY",
        user=current_user,
        details={
            "case_id": req.case_id,
            "passed": is_passed,
            "tre_error": tre_val,
            "threshold": threshold,
            "simulate_high_error": req.simulate_high_error
        }
    )

    tre_text = f"{tre_val:.2f} mm" if tre_val is not None else "N/A"
    return {
        "status": "SYNTHETIC_MATH_PASSED_L1_ONLY" if quality_passed else "SYNTHETIC_FIXTURE_REJECTED",
        "message": (
            f"Synthetic code fixture passed its TRE calculation ({tre_text} <= {threshold:.1f} mm), but remains L1 because it has no patient landmark provenance."
            if quality_passed
            else f"Synthetic code fixture failed its TRE gate ({tre_text} > {threshold:.1f} mm)."
        ),
        "held_out_tre": tre_val,
        "tau_tre_threshold": threshold,
        "is_gate_passed": is_passed,
        "registration_quality_passed": quality_passed,
        "fitting_error_rms": None,
        "anatomical_level": "L1_GENERIC",
        "assigned_region": None,
        "held_out_count": gate_result["held_out_count"],
        "mapping_status": gate_result["mapping_status"],
        "notice": "SYNTHETIC FIXTURE ONLY. Never convert a 2D coordinate or heatmap into an exact internal 3D location."
    }
