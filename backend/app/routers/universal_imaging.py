"""Authenticated additive geometry metadata; canonical readers own the pixels."""
from pathlib import Path
import json
import threading
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session
from pydantic import BaseModel, ConfigDict, Field

from app.database import get_db
from app.models.entities import InferenceRun, ModalityType, ReferenceAnnotation, User
from app.routers.modalities import DicomSeriesRequest, DicomSeriesRenderRequest, _upload, load_series, series_records
from app.services.auth import get_current_user, verify_case_access
from app.services import upload_store
from app.services.imaging_readers import ImagingReadError
from app.services.universal_geometry import GeometryRefusal, spatial_contract
from app.services.universal_spatial_io import source_metadata, view_contract, configure_view, read_selected_volume, render_plane
from app.services import universal_registration

router = APIRouter(tags=["Universal spatial evidence"])
_registration_lock = threading.Lock()


class RegistrationSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    upload_id: int = Field(ge=1)
    frame_index: int | None = Field(default=None, ge=0, le=4095)
    frame_kind: Literal["channel", "time"] | None = None


class PhysicalLandmark(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    fixed_ras_mm: tuple[float, float, float]
    moving_ras_mm: tuple[float, float, float]


class RegistrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    fixed: RegistrationSource
    moving: RegistrationSource
    same_subject_attested: bool = False
    same_anatomical_region_attested: bool = False
    metric: Literal["mattes", "mean_squares"] = "mattes"
    landmarks: list[PhysicalLandmark] = Field(default_factory=list, max_length=100)
    landmark_source: Literal["SYNTHETIC_KNOWN_TRANSFORM", "REVIEWER_SUPPLIED_UNVERIFIED", "INDEPENDENT_EXPERT_ATTESTED"] = "REVIEWER_SUPPLIED_UNVERIFIED"


@router.post("/cases/{case_id}/spatial/registration")
def candidate_registration(case_id: int, request: RegistrationRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    records = [_upload(selection.upload_id, db, current_user) for selection in [request.fixed, request.moving]]
    if any(record.case_id != case_id or record.modality != ModalityType.IMAGE for record in records):
        raise HTTPException(404, detail={"code": "SOURCES_NOT_IN_CASE"})
    if request.fixed == request.moving:
        raise HTTPException(422, detail={"code": "DISTINCT_SOURCES_REQUIRED", "reason": "A source cannot validate its own registration."})
    if not request.same_subject_attested or not request.same_anatomical_region_attested:
        raise HTTPException(422, detail={"code": "SOURCE_CORRESPONDENCE_ATTESTATION_REQUIRED", "reason": "Confirm same subject and anatomical region; case membership alone does not establish correspondence."})
    if not _registration_lock.acquire(blocking=False):
        raise HTTPException(429, detail={"code": "REGISTRATION_RESOURCE_BUSY"})
    try:
        arrays, contracts = [], []
        for record, selection in zip(records, [request.fixed, request.moving]):
            with upload_store.materialize(Path(record.file_path)) as plain:
                metadata = source_metadata(plain, selection.frame_index, selection.frame_kind)
                contract = view_contract(metadata, {"kind": "UPLOAD", "case_id": case_id, "upload_id": record.id, "sha256": record.file_hash})
                if contract["status"] != "AVAILABLE":
                    raise HTTPException(422, detail=contract["refusal"])
                if not contract["world_available"]:
                    raise HTTPException(422, detail=contract["world_refusal"])
                import math
                if math.prod(contract["dimensions_xyz"]) > universal_registration.MAX_REGISTRATION_VOXELS:
                    raise HTTPException(422, detail={"code": "REGISTRATION_INPUT_BOUNDS"})
                arrays.append(read_selected_volume(plain, metadata)); contracts.append(contract)
        result = universal_registration.register_rigid(arrays[0], contracts[0], arrays[1], contracts[1], landmarks=[landmark.model_dump() for landmark in request.landmarks], landmark_source=request.landmark_source, metric=request.metric)
        result["case_id"] = case_id
        result["sources"] = {name: {**selection.model_dump(), "sha256": record.file_hash} for name, selection, record in zip(["fixed", "moving"], [request.fixed, request.moving], records)}
        from app.services.audit_service import log_audit_event
        log_audit_event(db=db, action="RESEARCH_REGISTRATION_CANDIDATE", resource_type="CASE", resource_id=str(case_id), user=current_user, details={"fixed_upload_id": records[0].id, "moving_upload_id": records[1].id, "status": result["status"], "clinical_activation": False})
        return result
    except GeometryRefusal as exc:
        raise HTTPException(422, detail={"code": exc.code, "reason": exc.reason}) from exc
    except (ImagingReadError, ValueError, OSError) as exc:
        raise HTTPException(422, detail={"code": "REGISTRATION_SOURCE_UNREADABLE", "error_type": type(exc).__name__}) from exc
    finally:
        _registration_lock.release()


@router.get("/uploads/{file_id}/spatial/metadata")
def upload_spatial_metadata(file_id: int,
                            frame_index: int | None = Query(None, ge=0, le=4095),
                            frame_kind: Literal["channel", "time"] | None = None,
                            view_space: Literal["source", "anatomical"] = "source",
                            db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = _upload(file_id, db, current_user)
    if record.modality != ModalityType.IMAGE:
        raise HTTPException(400, detail={"code": "UNSUPPORTED_MODALITY", "reason": "Spatial viewing requires an imaging upload."})
    source = {"upload_id": record.id, "case_id": record.case_id, "sha256": record.file_hash, "kind": "UPLOAD"}
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            metadata = source_metadata(plain, frame_index, frame_kind)
            result = view_contract(metadata, source, view_space)
    except (ImagingReadError, ValueError, OSError) as exc:
        raise HTTPException(422, detail={"code": "SPATIAL_SOURCE_UNREADABLE", "reason": "Source could not be read safely.", "error_type": type(exc).__name__}) from exc
    result["render_input"] = {"kind": "UPLOAD", "upload_id": record.id, "path": f"/uploads/{record.id}/spatial/render",
                              "query": {"view_space": view_space, **({"frame_index": frame_index, "frame_kind": frame_kind} if frame_index is not None and frame_kind else {})}}
    return result


@router.get("/uploads/{file_id}/spatial/render")
def render_spatial_upload(file_id: int,
                          frame_index: int | None = Query(None, ge=0, le=4095),
                          frame_kind: Literal["channel", "time"] | None = None,
                          view_space: Literal["source", "anatomical"] = "source",
                          axis: Literal["axial", "coronal", "sagittal"] = "axial",
                          index: int | None = Query(None, ge=0, le=4095),
                          center: float | None = None, width: float | None = Query(None, gt=0),
                          layer: Literal["image", "prediction", "reviewer"] = "image",
                          run_id: int | None = Query(None, ge=1),
                          db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = _upload(file_id, db, current_user)
    if record.modality != ModalityType.IMAGE:
        raise HTTPException(400, detail={"code": "UNSUPPORTED_MODALITY"})
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            metadata = source_metadata(plain, frame_index, frame_kind)
            contract = view_contract(metadata, {"kind": "UPLOAD", "case_id": record.case_id, "upload_id": record.id, "sha256": record.file_hash}, view_space)
            if contract["status"] != "AVAILABLE":
                raise HTTPException(422, detail=contract["refusal"])
            if layer == "image":
                array = read_selected_volume(plain, metadata)
            else:
                from app.services import reference_annotations, volume_inference
                run = db.get(InferenceRun, run_id) if run_id else None
                if run is None or run.case_id != record.case_id or run.file_id != record.id:
                    raise HTTPException(404, detail={"code": "RUN_NOT_BOUND_TO_SOURCE"})
                provenance = (run.findings[0].evidence_provenance or {}) if run.findings else {}
                output = provenance.get("output") or {}
                if output.get("type") != "volume_segmentation" or output.get("volume_shape_ijk") != metadata.get("dimensions"):
                    raise HTTPException(422, detail={"code": "MASK_NATIVE_GRID_MISMATCH"})
                if provenance.get("source_file_sha256") not in {None, record.file_hash}:
                    raise HTTPException(409, detail={"code": "SOURCE_HASH_MISMATCH"})
                if frame_kind == "time" and metadata["frame_selection"]["required"] and provenance.get("source_frame_index") != frame_index:
                    raise HTTPException(422, detail={"code": "RUN_FRAME_BINDING_REQUIRED", "reason": "This run has no verified binding to the selected timepoint."})
                if layer == "prediction":
                    array = volume_inference.mask_from_output(output)
                else:
                    import numpy as np
                    array = np.zeros(metadata["dimensions"], dtype=np.uint8)
                    names = {item["structure"]: item["class_index"] for item in output["structures"]}
                    rows = db.query(ReferenceAnnotation).filter(ReferenceAnnotation.derived_from_run_id == run.id, ReferenceAnnotation.file_id == record.id, ReferenceAnnotation.kind == reference_annotations.VOLUME_SLICE).order_by(ReferenceAnnotation.id).all()
                    latest = {(row.slice_index, row.class_name): row for row in rows}
                    for (k, name), row in latest.items():
                        if name not in names or not 0 <= k < array.shape[2] or row.image_size != metadata["dimensions"][:2]:
                            raise HTTPException(422, detail={"code": "CORRECTION_NATIVE_GRID_MISMATCH"})
                        mask = reference_annotations.decode(row.rle).T
                        array[:, :, k][mask] = 1
            png, info = render_plane(array, contract, axis, index, center, width, categorical=layer != "image", reviewer=layer == "reviewer")
            info.update(layer=layer.upper(), source_upload_id=record.id, source_sha256=record.file_hash, run_id=run_id if layer != "image" else None)
    except GeometryRefusal as exc:
        raise HTTPException(422, detail={"code": exc.code, "reason": exc.reason}) from exc
    except (ImagingReadError, ValueError, OSError) as exc:
        raise HTTPException(422, detail={"code": "SPATIAL_SOURCE_UNREADABLE", "error_type": type(exc).__name__}) from exc
    return Response(png, media_type="image/png", headers={"X-MedTwin-Render": json.dumps(info, separators=(",", ":")), "Cache-Control": "private, no-store"})


@router.post("/cases/{case_id}/spatial/series-metadata")
def series_spatial_metadata(case_id: int, request: DicomSeriesRequest, view_space: Literal["source", "anatomical"] = "source", db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    records = series_records(case_id, request.upload_ids, db)
    # Apply the same current/withdrawn/superseded boundary as the individual reader.
    for record in records:
        _upload(record.id, db, current_user)
    report = load_series(records, request.series_reference, phase=request.phase)
    result = configure_view(spatial_contract(report, {"case_id": case_id, "kind": "DICOM_SERIES", "uploads": [{"upload_id": r.id, "sha256": r.file_hash} for r in records]}, series=True), view_space)
    report.pop("ordered_input_indices", None)
    result["series_report"] = report
    result["render_input"] = {"kind": "DICOM_SERIES", "path": f"/cases/{case_id}/spatial/series-render", "body": {**request.model_dump(), "view_space": view_space}}
    return result


class SpatialSeriesRenderRequest(DicomSeriesRenderRequest):
    view_space: Literal["source", "anatomical"] = "source"


@router.post("/cases/{case_id}/spatial/series-render")
def render_spatial_series(case_id: int, request: SpatialSeriesRenderRequest, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    verify_case_access(case_id, current_user, db, access="read")
    records = series_records(case_id, request.upload_ids, db)
    for record in records:
        _upload(record.id, db, current_user)
    report = load_series(records, request.series_reference, load_pixels=True, phase=request.phase)
    contract = configure_view(spatial_contract(report, {"case_id": case_id, "kind": "DICOM_SERIES"}, series=True), request.view_space)
    if contract["status"] != "AVAILABLE":
        raise HTTPException(422, detail=contract["refusal"])
    import numpy as np
    try:
        png, info = render_plane(np.transpose(report["volume"], (2, 1, 0)), contract, request.axis, request.index, request.center, request.width)
    except GeometryRefusal as exc:
        raise HTTPException(422, detail={"code": exc.code, "reason": exc.reason}) from exc
    return Response(png, media_type="image/png", headers={"X-MedTwin-Render": json.dumps(info, separators=(",", ":")), "Cache-Control": "private, no-store"})
