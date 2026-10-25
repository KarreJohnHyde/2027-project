"""Anatomy Studio API: system manifest, case evidence mapping, registration reviews."""

from __future__ import annotations

import json
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.config import ANATOMY_MANIFEST_PATH
from app.database import get_db
from app.models.entities import AnatomyRegistrationReview, User, UserRole
from app.services.anatomy_evidence import build_case_anatomy_evidence
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(tags=["Anatomy Studio"])


def _manifest() -> dict[str, Any]:
    try:
        return json.loads(ANATOMY_MANIFEST_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ANATOMY_MANIFEST_UNAVAILABLE: run tools/asset-pipeline (inspect, optimize, manifest).",
        )


@router.get("/anatomy/systems")
def list_anatomy_systems(current_user: User = Depends(get_current_user)):
    """The ten studio systems with variant summaries (full detail is in /anatomy/manifest.json)."""
    manifest = _manifest()
    variants = manifest["variants"]
    return {
        "schema_version": manifest["schema_version"],
        "generated_at_utc": manifest["generated_at_utc"],
        "representation_level": manifest["representation_level"],
        "notice": manifest["notice"],
        "mapping_categories": manifest["mapping_categories"],
        "systems": [
            {
                **{key: system[key] for key in ("id", "order", "label", "specialty", "summary", "default_variant", "limitations")},
                "variants": [
                    {
                        "id": variant_id,
                        "label": variants[variant_id]["label"],
                        "kind": variants[variant_id]["kind"],
                        "role": variants[variant_id]["role"],
                        "available": variants[variant_id]["available"],
                        "license_class": variants[variant_id]["license"]["class"],
                        "view_types": variants[variant_id]["view_types"],
                    }
                    for variant_id in system["variants"]
                ],
                "has_hybrid_layers": bool(system.get("hybrid")),
            }
            for system in manifest["systems"]
        ],
        "totals": manifest["totals"],
    }


@router.get("/cases/{case_id}/anatomy-evidence")
def get_case_anatomy_evidence(case_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Case evidence grouped by anatomical system with an explicit mapping category per item."""
    verify_case_access(case_id, current_user, db, access="read")
    return build_case_anatomy_evidence(db, case_id)


class RegistrationReviewCreate(BaseModel):
    layer_id: str = Field(..., max_length=96)
    decision: Literal["ACCEPTED_FOR_EDUCATIONAL_DISPLAY", "REJECTED", "NEEDS_LANDMARKS"]
    comments: Optional[str] = Field(None, max_length=2000)


def _serialize_review(review: AnatomyRegistrationReview) -> dict[str, Any]:
    return {
        "id": review.id,
        "layer_id": review.layer_id,
        "variant_id": review.variant_id,
        "target_frame": review.target_frame,
        "method": review.method,
        "transform": review.transform,
        "metrics": review.metrics,
        "decision": review.decision,
        "comments": review.comments,
        "reviewer_id": review.reviewer_id,
        "created_at": review.created_at.isoformat(),
    }


@router.get("/anatomy/registration-reviews")
def list_registration_reviews(layer_id: Optional[str] = None, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(AnatomyRegistrationReview)
    if layer_id:
        query = query.filter(AnatomyRegistrationReview.layer_id == layer_id)
    return [_serialize_review(row) for row in query.order_by(AnatomyRegistrationReview.created_at.desc()).all()]


@router.post("/anatomy/registration-reviews", status_code=status.HTTP_201_CREATED)
def create_registration_review(payload: RegistrationReviewCreate, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Record a reviewer decision on an unregistered or bbox-aligned hybrid layer.

    The transform and metrics are copied from the manifest so the decision is
    bound to exactly the placement that was reviewed. An accepted review never
    upgrades the layer to 'registered'; it permits educational display only.
    """
    if current_user.role not in (UserRole.CLINICIAN, UserRole.ADMIN, UserRole.RESEARCHER):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Reviewer role required.")
    manifest = _manifest()
    hybrid = next((system["hybrid"] for system in manifest["systems"] if system.get("hybrid")), None)
    layer = next((item for item in (hybrid or {}).get("layers", []) if item["id"] == payload.layer_id), None)
    if layer is None or layer["kind"] not in ("UNREGISTERED_COMPARISON", "ASSET_LAYER"):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Only unregistered or bbox-aligned hybrid layers are reviewable.")
    if layer["kind"] == "UNREGISTERED_COMPARISON":
        transform = layer["transform"]
        metrics = {key: transform.get(key) for key in ("scale", "residual_width_mm", "residual_depth_mm")}
    else:
        transform = {"translation_m": layer.get("translation_m")}
        metrics = layer.get("alignment")
    review = AnatomyRegistrationReview(
        layer_id=payload.layer_id,
        variant_id=layer["variant_id"],
        target_frame="Z_ANATOMY_ADULT_MALE_ATLAS_1_2_0",
        method=(layer.get("transform") or layer.get("alignment") or {}).get("method", "UNKNOWN"),
        transform=transform,
        metrics=metrics,
        decision=payload.decision,
        comments=payload.comments,
        reviewer_id=current_user.id,
    )
    db.add(review)
    db.commit()
    db.refresh(review)
    log_audit_event(
        db=db, action="ANATOMY_REGISTRATION_REVIEWED", resource_type="ANATOMY_LAYER", resource_id=payload.layer_id,
        user=current_user, details={"decision": payload.decision, "review_id": review.id},
    )
    return _serialize_review(review)
