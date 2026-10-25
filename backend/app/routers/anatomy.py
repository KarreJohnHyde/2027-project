"""
3D Anatomical Assets and Registration Gate Router for MedTwin.
Enforces the L1/L2/L3 representation taxonomy:
- L1 (Generic Reference Mesh): Default state.
- L2 (Finding-Associated): Gated by held-out Target Registration Error (TRE <= tau_TRE).
- L3 (Patient-Specific): Strictly prohibited unless full 3D volumetric reconstruction is validated.
"""

from pathlib import Path
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Finding, AnatomicalAsset, AnatomicalMapping, RepresentationLevel, User
from app.schemas.entities import AnatomicalAssetResponse, RegistrationGateCheck, RegistrationResponse
from app.services.auth import get_current_user, verify_case_access
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
    # The public request does not accept a self-asserted evidence-verification
    # flag. Until a reviewed landmark manifest is implemented, raw coordinates
    # may exercise TRE mathematics but cannot promote a finding beyond L1.
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
