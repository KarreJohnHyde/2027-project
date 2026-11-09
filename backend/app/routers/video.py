"""Endoscopy video uploads: metadata, single frames for display, and per-frame research inference (app.services.video_frames)."""

from __future__ import annotations

import io
from pathlib import Path
from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query, status
from fastapi.responses import JSONResponse, Response
from PIL import Image
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import InferenceRun, UploadedFile, User
from app.routers.research_models import serialize_research_run
from app.services import job_handlers  # noqa: F401 - registers the job handlers
from app.services import job_queue, model_inference, upload_store, video_frames
from app.services.auth import get_current_user, verify_case_access

router = APIRouter(tags=["Endoscopy video"])


def _video_upload(db: Session, file_id: int, user: User, access: str) -> UploadedFile:
    record = db.get(UploadedFile, file_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(record.case_id, user, db, access=access)
    if not video_frames.is_video(record.stored_filename):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VIDEO_REQUIRED: this endpoint reads MP4 or AVI video uploads.")
    if not record.is_associated or record.withdrawn_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unassociated uploads cannot enter case-level processing.")
    return record


@router.get("/uploads/{file_id}/video")
def get_video_metadata(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    record = _video_upload(db, file_id, current_user, "read")
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            return {"file_id": record.id, "filename": record.filename, **video_frames.probe(plain)}
    except video_frames.VideoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/uploads/{file_id}/video/frame")
def get_video_frame(file_id: int, index: int = Query(..., ge=0), db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """One decoded frame as PNG, in the frame's own pixels (the coordinate space of per-frame masks)."""
    record = _video_upload(db, file_id, current_user, "read")
    try:
        with upload_store.materialize(Path(record.file_path)) as plain:
            meta = video_frames.probe(plain)
            if index >= meta["frame_count"]:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"FRAME_OUT_OF_RANGE: the video has {meta['frame_count']} frames.")
            rgb = video_frames.read_frame(plain, index)
    except video_frames.VideoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    buffer = io.BytesIO()
    Image.fromarray(rgb).save(buffer, format="PNG")
    return Response(content=buffer.getvalue(), media_type="image/png", headers={"Cache-Control": "private, max-age=300"})


class VideoFrameRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    interval_s: float = Field(default=1.0, ge=video_frames.MIN_INTERVAL_S, le=video_frames.MAX_INTERVAL_S)
    max_frames: int = Field(default=120, ge=1, le=video_frames.MAX_SAMPLED_FRAMES)
    # The requesting user states that the video is a GI endoscopy recording.
    attest_gi_endoscopy_video: Literal[True]

    model_config = ConfigDict(extra="forbid")


@router.post("/uploads/{file_id}/video-frame-analysis", status_code=status.HTTP_201_CREATED,
             responses={202: {"description": "Queued for the background worker (worker execution mode)."}})
def run_video_frame_analysis(
    file_id: int,
    request: VideoFrameRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Sample frames and score each with a still-image endoscopy research model (queued on the GPU slot)."""
    record = _video_upload(db, file_id, current_user, "write")
    try:
        model = model_inference.get_model(request.model_id)
        video_frames.check_model(model)
        with upload_store.materialize(Path(record.file_path)) as plain:
            video_frames.probe(plain)
    except model_inference.InferenceNotPermitted as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except video_frames.VideoError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    key = f"video:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(db, "VIDEO_FRAME_ANALYSIS", payload={"model_id": request.model_id, "interval_s": request.interval_s,
                                                                         "max_frames": request.max_frames},
                                      requested_by=current_user, case_id=record.case_id, file_id=record.id, resource="GPU", idempotency_key=key)
    if job_queue.execution_mode() == "worker" and job.status not in job_queue.TERMINAL:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})
    if job.status == "QUEUED":
        claimed = job_queue.claim(db, f"api-inline:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is None:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The model runtime is busy; retry shortly.")
        job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    if job.status == "SUCCEEDED" and job.result_ref:
        return serialize_research_run(db.get(InferenceRun, job.result_ref["inference_run_id"]))
    if job.status == "RUNNING":
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Video frame analysis failed; the error state was recorded on the job.")
