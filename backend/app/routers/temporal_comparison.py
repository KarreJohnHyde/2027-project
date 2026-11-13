"""Authenticated, hash-bound matched-source temporal comparison candidates."""
import hashlib
import json
import math
from pathlib import Path

import numpy as np
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import ModalityType, User
from app.routers.modalities import _upload
from app.routers.universal_imaging import _registration_lock
from app.schemas.temporal_comparison import TemporalComparisonRequest, TemporalRenderRequest
from app.services import temporal_comparison as temporal, upload_store, universal_registration
from app.services.auth import get_current_user, verify_case_access
from app.services.imaging_readers import ImagingReadError
from app.services.universal_geometry import GeometryRefusal
from app.services.universal_spatial_io import configure_view, source_metadata, read_selected_volume, view_contract

router = APIRouter(tags=["Matched temporal imaging"])


def _load(selection: dict, case_id: int, db: Session, user: User):
    record = _upload(selection["upload_id"], db, user)
    if record.case_id != case_id or record.modality != ModalityType.IMAGE:
        raise HTTPException(404, detail={"code": "SOURCE_NOT_IN_COMPARISON_CASE"})
    if selection["sha256"] != record.file_hash:
        raise GeometryRefusal("SOURCE_HASH_CHANGED", "Source hash no longer matches the selected evidence.")
    with upload_store.materialize(Path(record.file_path)) as path:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        if digest != record.file_hash:
            raise GeometryRefusal("SOURCE_CONTENT_HASH_MISMATCH", "Stored source bytes do not match their verified upload identity.")
        metadata = source_metadata(path, selection.get("frame_index"), selection.get("frame_kind"))
        contract = view_contract(metadata, {"kind": "UPLOAD", "case_id": case_id, **selection})
        if contract["status"] != "AVAILABLE":
            raise GeometryRefusal(**contract["refusal"])
        if not contract["world_available"]:
            raise GeometryRefusal(**contract["world_refusal"])
        if math.prod(contract["dimensions_xyz"]) > temporal.MAX_INPUT_VOXELS:
            raise GeometryRefusal("COMPARISON_INPUT_BOUNDS", "Each comparison source is limited to 32 million voxels.")
        evidence = temporal.intensity_evidence(path, metadata)
        array = read_selected_volume(path, metadata)
    return array, contract, evidence


def _refusal(exc: Exception):
    if isinstance(exc, GeometryRefusal):
        return HTTPException(404 if exc.code == "COMPARISON_NOT_FOUND" else 422, detail={"code": exc.code, "reason": exc.reason})
    return HTTPException(422, detail={"code": "COMPARISON_SOURCE_UNREADABLE", "error_type": type(exc).__name__})


@router.post("/cases/{case_id}/temporal-comparisons")
def create_comparison(case_id: int, request: TemporalComparisonRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    try:
        if not request.same_subject_attested or not request.same_region_attested:
            raise GeometryRefusal("COMPARISON_CORRESPONDENCE_REQUIRED", "Confirm the same subject and anatomical region; case membership is insufficient.")
        if " ".join(request.previous_region.casefold().split()) != " ".join(request.current_region.casefold().split()):
            raise GeometryRefusal("ANATOMICAL_REGION_MISMATCH", "Declared anatomical regions do not match.")
        previous, current = request.previous.model_dump(), request.current.model_dump()
        if previous == current or (previous["sha256"] == current["sha256"] and (previous["frame_kind"] != "time" or current["frame_kind"] != "time" or previous["frame_index"] == current["frame_index"])):
            raise GeometryRefusal("DISTINCT_TIMEPOINT_SOURCES_REQUIRED", "Identical source content/frame cannot establish a temporal comparison.")
        if previous["frame_kind"] == "channel" or current["frame_kind"] == "channel":
            if previous["upload_id"] == current["upload_id"] or previous["frame_kind"] != current["frame_kind"] or previous["frame_index"] != current["frame_index"]:
                raise GeometryRefusal("CHANNEL_PROTOCOL_MISMATCH", "Different sequences/channels are not interchangeable temporal studies.")
        arrays, contracts, intensity = [], [], []
        for source in [previous, current]:
            array, contract, evidence = _load(source, case_id, db, current_user)
            arrays.append(array); contracts.append(contract); intensity.append(evidence)
        intensity_contract = temporal.compatibility(*intensity, request.comparable_intensity_attested)
        registration = None
        if request.alignment == "compute_rigid":
            if not _registration_lock.acquire(blocking=False):
                raise HTTPException(429, detail={"code": "REGISTRATION_RESOURCE_BUSY"})
            try:
                registration = universal_registration.register_rigid(arrays[0], contracts[0], arrays[1], contracts[1], metric=request.metric)
            finally:
                _registration_lock.release()
            transform = temporal.validate_rigid(registration["fixed_to_moving_ras_mm"])
            alignment_evidence = "CANONICAL_RIGID_OPTIMIZER_CANDIDATE"
        elif request.alignment == "shared_physical_space":
            if not request.shared_physical_space_attested:
                raise GeometryRefusal("SHARED_SPACE_ATTESTATION_REQUIRED", "Coded source geometry does not prove anatomical alignment. Explicitly attest pre-existing shared physical space.")
            transform = np.eye(4); alignment_evidence = "SHARED_SPACE_ATTESTED_NOT_INDEPENDENTLY_VERIFIED"
        else:
            supplied = request.provided_rigid
            if supplied is None or supplied.previous.model_dump() != previous or supplied.current.model_dump() != current:
                raise GeometryRefusal("TRANSFORM_SOURCE_BINDING_MISMATCH", "Provided transform must bind both exact source hashes, upload IDs and frame selectors.")
            transform = temporal.validate_rigid(supplied.previous_to_current_ras_mm)
            alignment_evidence = "PROVIDED_RIGID_NOT_INDEPENDENTLY_VERIFIED"
        reference = configure_view(dict(contracts[0]), "anatomical")
        if reference["status"] != "AVAILABLE":
            raise GeometryRefusal(**reference["refusal"])
        public = {"schema_version": "medtwin.temporal-comparison.v1", "status": "CANDIDATE_UNVALIDATED", "sources": {"previous": previous, "current": current},
                  "declared_region": request.previous_region, "alignment_evidence": alignment_evidence,
                  "previous_to_current_ras_mm": transform.tolist(), "current_to_previous_ras_mm": np.linalg.inv(transform).tolist(),
                  "reference_grid": {key: reference[key] for key in ["dimensions_xyz", "spacing_xyz_mm", "affine_voxel_to_world", "coordinate_frame"]},
                  "intensity": intensity_contract, "registration": registration,
                  "clinical_progression_claim": False, "clinical_activation": False, "atlas_registration": False,
                  "resource_bounds": {"max_source_voxels": temporal.MAX_INPUT_VOXELS, "max_plane_pixels": 1024*1024, "max_live_sessions": temporal.MAX_SESSIONS},
                  "semantics": "Matched source-space research comparison candidate. Registration/alignment is unvalidated; pixel differences do not establish disease progression, treatment response or a diagnosis."}
        value = {"public": public, "previous": previous, "current": current, "reference": reference, "current_contract": contracts[1], "transform": transform.tolist()}
        return temporal.put_session(current_user.id, case_id, value)
    except (GeometryRefusal, ImagingReadError, ValueError, OSError) as exc:
        raise _refusal(exc) from exc


@router.post("/cases/{case_id}/temporal-comparisons/{comparison_id}/render")
def comparison_render(case_id: int, comparison_id: str, request: TemporalRenderRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    try:
        session = temporal.get_session(comparison_id, current_user.id, case_id)
        arrays = [_load(session[key], case_id, db, current_user)[0] for key in ["previous", "current"]]
        png, info = temporal.render_comparison(arrays[0], arrays[1], session, request)
        info.update(comparison_id=comparison_id, sources=session["public"]["sources"])
        return Response(png, media_type="image/png", headers={"X-MedTwin-Comparison": json.dumps(info, separators=(",", ":")), "Cache-Control": "private, no-store"})
    except (GeometryRefusal, ImagingReadError, ValueError, OSError) as exc:
        raise _refusal(exc) from exc
