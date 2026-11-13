"""Bounded source-to-source comparison; difference pixels are not disease progression."""
from __future__ import annotations
import io
import secrets
import threading
import time
from collections import OrderedDict
from pathlib import Path

import numpy as np
from PIL import Image
from app.services.universal_geometry import GeometryRefusal, validate_affine
from app.services.universal_spatial_io import _ras_affine, sample_plane

SESSION_TTL_SECONDS = 600
MAX_SESSIONS = 32
MAX_INPUT_VOXELS = 32_000_000
_sessions: OrderedDict[str, dict] = OrderedDict()
_lock = threading.Lock()


def validate_rigid(value) -> np.ndarray:
    matrix = validate_affine(value)
    rotation = matrix[:3, :3]
    if not np.allclose(rotation.T @ rotation, np.eye(3), atol=1e-5) or not np.isclose(np.linalg.det(rotation), 1., atol=1e-5):
        raise GeometryRefusal("NON_RIGID_TRANSFORM", "Comparison accepts proper rigid transforms only; scale, shear and reflection are refused.")
    if np.linalg.norm(matrix[:3, 3]) > 2000:
        raise GeometryRefusal("TRANSFORM_TRANSLATION_BOUNDS", "Transform translation exceeds the bounded comparison domain.")
    return matrix


def intensity_evidence(path: Path, metadata: dict) -> dict:
    """Only actual encoded intensity metadata qualify; a UI attestation is insufficient."""
    if metadata.get("container") == "NIFTI":
        import nibabel as nib
        header = nib.load(str(path)).header
        intent = bytes(header["intent_name"]).rstrip(b"\x00").decode("ascii", errors="ignore")
        description = bytes(header["descrip"]).rstrip(b"\x00").decode("ascii", errors="ignore")
        if intent == "MT_SYNTHETIC" and description == "MedTwin original synthetic control;unit=matched_arbitrary":
            return {"modality": "ORIGINAL_SYNTHETIC_CONTROL", "unit": "MATCHED_ARBITRARY", "metadata_verified": True, "clinical_unit": False}
    tags = metadata.get("technical_tags") or {}
    if metadata.get("container") == "DICOM" and tags.get("Modality") == "CT" and tags.get("RescaleType") == "HU" and "RescaleSlope" in tags and "RescaleIntercept" in tags:
        return {"modality": "CT", "unit": "HU", "metadata_verified": True, "clinical_unit": True}
    return {"modality": metadata.get("modality_tag") or "UNSPECIFIED", "unit": None, "metadata_verified": False, "clinical_unit": False}


def compatibility(previous: dict, current: dict, attested: bool) -> dict:
    known_modalities = [entry["modality"] for entry in [previous, current] if entry["modality"] != "UNSPECIFIED"]
    if len(known_modalities) == 2 and known_modalities[0] != known_modalities[1]:
        raise GeometryRefusal("MODALITY_MISMATCH", "Actual source modality metadata do not match.")
    permitted = bool(attested and previous["metadata_verified"] and current["metadata_verified"] and previous["unit"] == current["unit"] and previous["modality"] == current["modality"])
    return {"difference_allowed": permitted, "previous": previous, "current": current,
            "refusal": None if permitted else {"code": "INTENSITY_COMPATIBILITY_UNVERIFIED", "reason": "Raw intensity units/protocol compatibility are not verified by source metadata. An attestation alone cannot enable quantitative difference."},
            "semantics": "Difference is raw current-minus-previous intensity on valid overlap, not clinical progression or lesion growth."}


def put_session(user_id: int, case_id: int, value: dict) -> dict:
    now = time.monotonic()
    with _lock:
        for key in list(_sessions):
            if _sessions[key]["expires_monotonic"] <= now:
                del _sessions[key]
        while len(_sessions) >= MAX_SESSIONS:
            _sessions.popitem(last=False)
        token = secrets.token_hex(16)
        _sessions[token] = {**value, "user_id": user_id, "case_id": case_id, "expires_monotonic": now+SESSION_TTL_SECONDS}
    return {"comparison_id": token, "expires_in_seconds": SESSION_TTL_SECONDS, **value["public"]}


def get_session(token: str, user_id: int, case_id: int) -> dict:
    with _lock:
        value = _sessions.get(token)
        if value is None or value["user_id"] != user_id or value["case_id"] != case_id:
            raise GeometryRefusal("COMPARISON_NOT_FOUND", "Comparison is unavailable for this user and case.")
        if value["expires_monotonic"] <= time.monotonic():
            del _sessions[token]
            raise GeometryRefusal("COMPARISON_EXPIRED", "Recreate the source-bound comparison; its ten-minute lease expired.")
        _sessions.move_to_end(token)
        return value


def comparison_planes(previous: np.ndarray, current: np.ndarray, reference: dict, current_contract: dict, transform: list, axis: str, index: int | None):
    matrix = validate_rigid(transform)
    current_view = {**reference, "view_to_native_voxel": (np.linalg.inv(_ras_affine(current_contract)) @ matrix @ reference["affine_voxel_to_world"]).tolist()}
    left, info = sample_plane(previous, reference, axis, index)
    right, _ = sample_plane(current, current_view, axis, index)
    left, right = left.astype(np.float64), right.astype(np.float64)
    valid = np.isfinite(left) & np.isfinite(right)
    return left, right, valid, info


def render_comparison(previous: np.ndarray, current: np.ndarray, session: dict, request) -> tuple[bytes, dict]:
    if request.mode == "difference" and not session["public"]["intensity"]["difference_allowed"]:
        refusal = session["public"]["intensity"]["refusal"]
        raise GeometryRefusal(refusal["code"], refusal["reason"])
    left, right, valid, info = comparison_planes(previous, current, session["reference"], session["current_contract"], session["transform"], request.axis, request.index)
    if left.size > 1024*1024:
        raise GeometryRefusal("COMPARISON_PIXEL_BOUNDS", "Comparison plane exceeds one million pixels.")
    pooled = np.concatenate([left[valid], right[valid]])
    if not pooled.size:
        raise GeometryRefusal("NO_VALID_OVERLAP", "This plane has no valid shared source field of view. No change can be measured here.")
    if request.center is not None and request.width is not None:
        low, high = request.center-request.width/2, request.center+request.width/2
    else:
        low, high = np.percentile(pooled, [.5, 99.5])
    high = max(float(high), float(low)+1e-8)
    a, b = [np.clip(np.nan_to_num((plane-low)/(high-low), nan=0), 0, 1) for plane in [left, right]]
    rgb = np.zeros((*left.shape, 3), dtype=np.uint8)
    delta = np.where(valid, right-left, 0)
    if request.mode == "difference":
        scale = request.difference_scale or max(float(np.percentile(np.abs(delta[valid]), 99)), 1e-8)
        signed = np.clip(delta/scale, -1, 1)
        rgb[:, :, 0] = (np.maximum(signed, 0)*255).astype(np.uint8)
        rgb[:, :, 2] = (np.maximum(-signed, 0)*255).astype(np.uint8)
        info["difference_scale"] = scale
    else:
        if request.mode == "previous": pixels = a
        elif request.mode == "current": pixels = b
        elif request.mode == "blend": pixels = (1-request.blend)*a + request.blend*b
        else:
            yy, xx = np.indices(left.shape); pixels = np.where((xx//24+yy//24)%2 == 0, a, b)
        rgb[:] = (pixels[:, :, None]*255).astype(np.uint8)
    # Invalid/out-of-FOV areas are visibly hatched, never assigned a difference value.
    yy, xx = np.indices(left.shape)
    rgb[~valid] = np.where((((xx+yy)//6)%2)[~valid, None] == 0, [25, 35, 45], [45, 55, 65])
    stats = {"valid_pixels": int(valid.sum()), "total_pixels": int(valid.size), "valid_fraction": float(valid.mean()), "invalid_pixels_excluded": True}
    if session["public"]["intensity"]["difference_allowed"]:
        stats.update(mean_current_minus_previous=float(delta[valid].mean()), mean_absolute_difference=float(np.abs(delta[valid]).mean()), p95_absolute_difference=float(np.percentile(np.abs(delta[valid]), 95)))
    info.update(mode=request.mode, window={"low": float(low), "high": float(high), "basis": "SAME_POOLED_VALID_OVERLAP_WINDOW"}, statistics=stats,
                status="CANDIDATE_UNVALIDATED", clinical_progression_claim=False, difference_semantics=session["public"]["intensity"]["semantics"])
    output = io.BytesIO(); Image.fromarray(rgb).save(output, format="PNG")
    return output.getvalue(), info
