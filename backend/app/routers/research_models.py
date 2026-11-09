"""Research-only inference with registered MedTwin models.

Runs go through the durable job queue (GPU resource). Outputs stay labelled
RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED and pending human review; boxes and masks
are returned in the source image's pixel coordinates for overlay.
"""

from pathlib import Path
import hashlib
import json
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, selectinload

from app.database import get_db
from app.models.entities import Finding, HumanReview, InferenceRun, ModalityType, ReferenceAnnotation, UploadedFile, User
from app.routers.jobs import serialize_analysis_job
from app.services import job_handlers  # noqa: F401 - registers the job handlers
from app.services import ct_organ_research, cxr_research, job_queue, model_inference, model_router, reference_annotations, upload_store, volume_inference
from app.services.anatomy_evidence import _latest_reviews, account_standing, reviewer_standing
from app.services.auth import get_current_user, verify_case_access
from app.services.imaging_readers import ImagingReadError, read_metadata
from app.services.model_registry import RegistryConfigurationError

router = APIRouter(tags=["Research Models"])

NOTICE = ("Research-only models trained on public datasets and evaluated on internal held-out splits. "
          "Not clinically validated; outputs require human review and must not be used for diagnosis.")


class SkinClinicalFeatures(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    age: float = Field(ge=0, le=120, strict=True)
    region: str = Field(min_length=1, max_length=40)
    gender: Optional[Literal["MALE", "FEMALE"]] = None


class ResearchInferenceRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    # Every key of model_inference.MODALITY_LABELS (a test keeps the two in step).
    declared_input_type: Literal["ENDOSCOPY", "ANGIOGRAPHY", "CT", "MICROSCOPY", "ECG", "MRI", "XRAY", "HEAD_CT",
                                 "BRAIN_MRI_DIFFUSION", "BRAIN_MRI_MULTISEQUENCE", "ECHO", "CT_ABDOMEN_VOLUME", "HEAD_CT_SERIES", "CHEST_XRAY",
                                 "CT_CHEST_VOLUME", "DERMATOLOGY"]
    # WFDB records are a header plus a signal file uploaded separately; CSV records carry no amplitude unit.
    companion_upload_id: Optional[int] = Field(default=None, ge=1)
    amplitude_unit: Optional[Literal["mV", "uV"]] = None
    # Demographic-fusion ECG models only; when absent, the case's latest reviewed demographics are used.
    age_years: Optional[float] = Field(default=None, ge=0, le=120)
    sex: Optional[Literal["M", "F"]] = None
    # Multi-frame DICOM uploads to a 2-D model: the frame to analyse (0-based).
    frame_index: Optional[int] = Field(default=None, ge=0, le=100_000)
    clinical_features: Optional[SkinClinicalFeatures] = None

    def options(self) -> dict:
        return {"companion_upload_id": self.companion_upload_id, "amplitude_unit": self.amplitude_unit,
                **({"age_years": self.age_years} if self.age_years is not None else {}), **({"sex": self.sex} if self.sex else {}),
                **({"frame_index": self.frame_index} if self.frame_index is not None else {}),
                **({"clinical_features": self.clinical_features.model_dump(exclude_none=True)} if self.clinical_features else {})}


class MultimodelRequest(ResearchInferenceRequest):
    model_id: str = "batch"
    model_ids: list[str] = Field(min_length=1, max_length=6)


class RoutingRequest(ResearchInferenceRequest):
    model_config = ConfigDict(extra="forbid")
    model_id: Literal["auto"] = "auto"
    declared_input_type: Optional[str] = Field(default=None, max_length=64)
    task: Literal["auto", "classification", "detection", "segmentation", "ef_regression", "document_extraction", "forecast"] = "auto"
    target: Optional[str] = Field(default=None, max_length=128)
    anatomy: Optional[str] = Field(default=None, max_length=128)
    attest_source_input: bool = False


@router.post("/uploads/{file_id}/model-selection")
def select_upload_model(file_id: int, request: RoutingRequest, db: Session = Depends(get_db),
                        current_user: User = Depends(get_current_user)):
    upload = _image_upload(db, file_id, current_user, "read")
    return model_router.plan_upload(upload, declared_input_type=request.declared_input_type, task=request.task,
                                    target=request.target, anatomy=request.anatomy, options=request.options(), db=db)


@router.post("/uploads/{file_id}/automatic-inference")
def run_automatic_inference(file_id: int, request: RoutingRequest,
                            idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
                            db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    upload = _image_upload(db, file_id, current_user, "write")
    plan = model_router.plan_upload(upload, declared_input_type=request.declared_input_type, task=request.task,
                                    target=request.target, anatomy=request.anatomy, options=request.options(), db=db)
    if plan["status"] != "SELECTED":
        raise HTTPException(status_code=409, detail=plan)
    if plan["handler"] == "report_analysis":
        from app.routers.analysis import trigger_file_analysis
        return trigger_file_analysis(file_id=file_id, idempotency_key=idempotency_key, db=db, current_user=current_user)
    if not request.attest_source_input:
        raise HTTPException(status_code=400, detail="SOURCE_ATTESTATION_REQUIRED: confirm the adapter's full source input contract.")
    # Reuse checkpoint, content/OOD, access, queue and provenance guards without an alternate inference path.
    selected = ResearchInferenceRequest(model_id=plan["selected_model_id"], declared_input_type=plan["declared_input_type"], **request.options())
    return run_research_inference(file_id, selected, idempotency_key, db, current_user)


@router.post("/uploads/{file_id}/multimodel", status_code=202)
def run_multimodel(file_id: int, request: MultimodelRequest, db: Session = Depends(get_db),
                   current_user: User = Depends(get_current_user)):
    upload = _image_upload(db, file_id, current_user, "write")
    if not upload.is_associated or upload.withdrawn_at is not None or upload.superseded_by_file_id is not None:
        raise HTTPException(status_code=409, detail="Upload is not active evidence.")
    if len(set(request.model_ids)) != len(request.model_ids):
        raise HTTPException(status_code=400, detail="Duplicate model ids are not independent analyses.")
    if any(len(model_id) > 128 or not model_id for model_id in request.model_ids):
        raise HTTPException(status_code=400, detail="Invalid model id.")
    job, _ = job_queue.enqueue(db, "MULTIMODEL_INFERENCE", payload={"model_ids": request.model_ids,
                                "declared_input_type": request.declared_input_type, "options": request.options()},
                               requested_by=current_user, case_id=upload.case_id, file_id=upload.id, resource="GPU")
    if job_queue.execution_mode() == "inline":
        claimed = job_queue.claim(db, f"api-inline:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is not None:
            job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    return {"queued_job": job_queue.serialize(job), "probability_combination": "NOT_ESTABLISHED",
            "notice": "Separate model outputs and abstentions retained; unrelated or uncalibrated probabilities are never averaged."}


def serialize_research_run(run: InferenceRun, review: Optional[HumanReview] = None) -> dict:
    payload = serialize_analysis_job(run)
    finding: Optional[Finding] = run.findings[0] if run.findings else None
    provenance = (finding.evidence_provenance or {}) if finding else {}
    payload["finding_id"] = finding.id if finding else None
    payload["research_output"] = provenance.get("output")
    payload["research_provenance"] = {key: value for key, value in provenance.items() if key != "output"}
    payload["latest_review"] = None if review is None else {
        "review_id": review.id, "review_status": review.review_status, "reviewer_id": review.reviewer_id,
        "reviewer_comments": review.reviewer_comments, "reviewed_at": review.reviewed_at.isoformat() if review.reviewed_at else None,
        "original_output_preserved": review.original_output_preserved,
        **reviewer_standing(review),
    }
    return payload


def _image_upload(db: Session, file_id: int, user: User, access: str) -> UploadedFile:
    file_record = db.get(UploadedFile, file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, user, db, access=access)
    return file_record


@router.get("/research-models")
def list_research_models(current_user: User = Depends(get_current_user)):
    try:
        models = model_inference.inference_models()
    except RegistryConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"notice": NOTICE, "input_types": model_inference.MODALITY_LABELS, "models": models}


@router.get("/research-learning")
def research_learning_status(current_user: User = Depends(get_current_user)):
    root = Path(__file__).resolve().parents[3]
    path = root / "artifacts/research_learning/bloodmnist-v1/report.json"
    report = json.loads(path.read_text(encoding="utf-8")) if path.exists() else None
    return {"clinical_activation": False, "automatic_upload_retraining": False,
            "strategies": ["train-only PCA + IsolationForest novelty", "seed-label self-training classifier",
                           "offline masked Q-learning for analysis workflow selection"],
            "notice": "Public-data experiments only. Novelty is not disease; workflow rewards are not treatment benefit. Uploaded patient data is not used for automatic retraining.",
            "benchmark": report, "report_sha256": hashlib.sha256(path.read_bytes()).hexdigest() if report else None}


@router.get("/research-models/{model_id}/evaluation")
def get_research_model_evaluation(model_id: str, current_user: User = Depends(get_current_user)):
    """The model's held-out evaluation report as written by ml_training (public-dataset results)."""
    model = next((item for item in model_inference._load_registry()["models"] if item["model_id"] == model_id and item.get("research_inference")), None)
    if model is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="No research model with this id.")
    try:
        report = model_inference._report(model)
    except (OSError, ValueError) as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Evaluation report unavailable: {type(exc).__name__}")
    return {"model_id": model_id, "task": model["task"], "gate": model_inference.research_gate(model), "report": report}


@router.post("/uploads/{file_id}/research-inference", status_code=status.HTTP_201_CREATED,
             responses={202: {"description": "Queued for the background worker (worker execution mode)."}})
def run_research_inference(
    file_id: int,
    request: ResearchInferenceRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    file_record = db.get(UploadedFile, file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, current_user, db)
    try:
        model = model_inference.get_model(request.model_id)
        companion = model_inference.check_input(model, file_record, request.declared_input_type, request.options(), db)
        # Signal and volume content is checked here too, so an out-of-contract upload is a typed refusal, not a failed job.
        model_inference.prepare_input(model, file_record, companion, request.options(), db, request.declared_input_type)
    except model_inference.InferenceNotPermitted as exc:
        if str(exc).startswith("MODEL_INPUT_"):
            model_inference.record_abstention(db, file_record, request.model_id, str(exc), current_user)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    key = f"research:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(
        db, "RESEARCH_MODEL_INFERENCE", payload={"model_id": request.model_id, "declared_input_type": request.declared_input_type, **request.options()},
        requested_by=current_user, case_id=file_record.case_id, file_id=file_record.id, resource="GPU", idempotency_key=key,
    )
    if job_queue.execution_mode() == "worker" and job.status not in job_queue.TERMINAL:
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})
    if job.status == "QUEUED":
        claimed = job_queue.claim(db, f"api-inline:{job_queue.default_worker_id()}", job_id=job.id)
        if claimed is None:
            # Inline mode has no worker: the GPU slot is busy, and a repeated request
            # reuses this queued job and claims it once the slot is free.
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="The model runtime is busy; retry shortly.")
        job = job_queue.run_claimed(db, claimed, claimed.lease_owner)
    if job.status == "SUCCEEDED" and job.result_ref:
        return serialize_research_run(db.get(InferenceRun, job.result_ref["inference_run_id"]))
    if job.status == "RUNNING":
        return JSONResponse(status_code=status.HTTP_202_ACCEPTED, content={"queued_job": job_queue.serialize(job)})
    refusal = "InferenceNotPermitted: "
    if job.status == "FAILED" and (job.last_error or "").startswith(refusal):
        # A content gate that needs the network (printed document, applicability reference) refused the image.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=job.last_error[len(refusal):])
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Research inference failed; the error state was recorded in provenance.")


@router.get("/uploads/{file_id}/research-inference")
def list_upload_research_inference(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Earlier research runs on this upload, newest first, each with its latest human review,
    so a stored mask or box set is shown again after a reload."""
    file_record = _image_upload(db, file_id, current_user, "read")
    try:
        research_ids = {model["model_id"] for model in model_inference._load_registry()["models"] if model.get("research_inference")}
        research_ids.add(ct_organ_research.MODEL_ID)  # third-party, run through its own endpoint
    except RegistryConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    runs = (db.query(InferenceRun).options(selectinload(InferenceRun.findings))
            .filter(InferenceRun.file_id == file_record.id, InferenceRun.model_name.in_(research_ids))
            .order_by(InferenceRun.id.desc()).limit(50).all())
    reviews = _latest_reviews(db, {run.findings[0].id for run in runs if run.findings})
    return {"file_id": file_record.id, "runs": [serialize_research_run(run, reviews.get(run.findings[0].id) if run.findings else None) for run in runs]}


def _reference_grid(file_record: UploadedFile, what: str) -> tuple[int, int]:
    """(width, height) of the pixel grid a reference attaches to: the upright raster, or a single-frame DICOM's columns and rows."""
    suffix = Path(file_record.stored_filename).suffix.lower()
    if file_record.modality != ModalityType.IMAGE or suffix not in model_inference.IMAGE_2D_SUFFIXES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"INPUT_NOT_SUPPORTED: reference {what} attach to PNG, JPEG or BMP image uploads, or a single-frame DICOM.")
    try:
        with upload_store.materialize(Path(file_record.file_path)) as plain:
            metadata = read_metadata(plain)  # upright size, EXIF orientation applied
    except ImagingReadError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    if suffix == ".dcm" and int(metadata.get("slices") or 1) > 1:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"MULTI_FRAME_DICOM: reference {what} attach to a single-frame DICOM; this file holds {metadata['slices']} frames.")
    width, height = metadata["dimensions"][:2]
    return int(width), int(height)


def _exif_orientation(file_record: UploadedFile) -> int:
    with upload_store.materialize(Path(file_record.file_path)) as plain:
        return int(read_metadata(plain).get("exif_orientation") or 1)


@router.post("/uploads/{file_id}/reference-annotations", status_code=status.HTTP_201_CREATED)
def add_reference_annotation(
    file_id: int,
    mask: UploadFile = File(...),
    source: str = Form(...),
    source_detail: str = Form(..., min_length=3, max_length=256),
    class_name: str = Form(..., min_length=1, max_length=64),
    binarize_threshold: int = Form(127, ge=0, le=254),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach a reference mask (GROUND_TRUTH layer) to an image upload; model output is untouched."""
    file_record = _image_upload(db, file_id, current_user, "write")
    if source not in reference_annotations.UPLOADABLE_SOURCES:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail="SOURCE_UNSUPPORTED: an uploaded reference must be independent of model output; corrections of a model mask "
                                   "are saved from the run (POST /research-inference/{run_id}/mask-corrections).")
    # A plain def runs in the threadpool: decryption, decoding and the commit stay off the event loop.
    content = mask.file.read(reference_annotations.MAX_MASK_BYTES + 1)
    width, height = _reference_grid(file_record, "masks")
    try:
        annotation = reference_annotations.create(db, file_record, [width, height], content, mask.filename or "mask", source,
                                                  source_detail, class_name, binarize_threshold, current_user)
    except reference_annotations.ReferenceAnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return reference_annotations.serialize(annotation)


@router.post("/uploads/{file_id}/reference-boxes", status_code=status.HTTP_201_CREATED)
def add_reference_boxes(
    file_id: int,
    boxes: UploadFile = File(...),
    source: str = Form(...),
    source_detail: str = Form(..., min_length=3, max_length=256),
    class_name: str = Form(..., min_length=1, max_length=64),
    yolo_class: Optional[int] = Form(None, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Attach reference boxes (GROUND_TRUTH layer: JSON or YOLO text, in this image's pixels) to an image upload."""
    file_record = _image_upload(db, file_id, current_user, "write")
    content = boxes.file.read(reference_annotations.MAX_MASK_BYTES + 1)
    width, height = _reference_grid(file_record, "boxes")
    try:
        annotation = reference_annotations.create_boxes(db, file_record, [width, height], content, boxes.filename or "boxes", source,
                                                        source_detail, class_name, current_user, yolo_class)
    except reference_annotations.ReferenceAnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return reference_annotations.serialize(annotation)


@router.post("/research-inference/{run_id}/mask-corrections", status_code=status.HTTP_201_CREATED)
def add_mask_correction(
    run_id: int,
    mask: UploadFile = File(...),
    class_name: str = Form(..., min_length=1, max_length=64),
    note: str = Form("", max_length=160),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a reviewer's brush/eraser edit of a 2-D segmentation run's mask (REVIEWER_CORRECTION layer).

    The run and its output stay unchanged; the correction is stored beside it with the run it came from and
    whether the reviewer was a verified clinician, and is returned with its agreement with the run's mask."""
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    file_record = _image_upload(db, run.file_id, current_user, "write")
    output = ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None
    if not output or output.get("type") != "segmentation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="SEGMENTATION_RUN_REQUIRED: only 2-D segmentation masks can be corrected here.")
    if "exif_orientation_applied" not in output and _exif_orientation(file_record) != 1:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="RUN_ON_UNORIENTED_GRID: this run predates EXIF orientation handling and this image is stored rotated or mirrored; re-run the model.")
    content = mask.file.read(reference_annotations.MAX_MASK_BYTES + 1)
    standing = account_standing(current_user)
    detail = (f"Reviewer correction of run {run.id} ({run.model_name}) by a "
              f"{'verified clinician' if standing['verified_professional'] else 'reviewer who is not a verified clinician'}"
              + (f": {note.strip()}" if note.strip() else ""))[:256]
    try:
        annotation = reference_annotations.create(db, file_record, list(output["image_size"]), content, mask.filename or "correction.png",
                                                  reference_annotations.CORRECTION, detail, class_name, 127, current_user, derived_from_run_id=run.id)
        comparison = reference_annotations.compare(output, annotation, run.id)
    except reference_annotations.ReferenceAnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {**reference_annotations.serialize(annotation), "comparison_with_run": {"run_id": run.id, **comparison}}


@router.post("/research-inference/{run_id}/volume-slice-corrections", status_code=status.HTTP_201_CREATED)
def add_volume_slice_correction(
    run_id: int,
    mask: UploadFile = File(...),
    slice_index: int = Form(..., ge=0),
    class_name: str = Form(..., min_length=1, max_length=64),
    note: str = Form("", max_length=160),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Save a reviewer's edit of one axial plane of a volumetric run's mask; the run itself is unchanged."""
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    file_record = _image_upload(db, run.file_id, current_user, "write")
    output = ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None
    standing = account_standing(current_user)
    detail = (f"Reviewer correction of slice {slice_index} of run {run.id} ({run.model_name}) by a "
              f"{'verified clinician' if standing['verified_professional'] else 'reviewer who is not a verified clinician'}"
              + (f": {note.strip()}" if note.strip() else ""))
    try:
        annotation = reference_annotations.create_volume_slice_correction(db, file_record, run.id, output, slice_index, class_name,
                                                                          mask.file.read(reference_annotations.MAX_MASK_BYTES + 1), detail, current_user)
        rows = db.query(ReferenceAnnotation).filter(ReferenceAnnotation.derived_from_run_id == run.id,
                                                    ReferenceAnnotation.kind == reference_annotations.VOLUME_SLICE).all()
        summary = reference_annotations.volume_corrections_summary(output, rows)
    except reference_annotations.ReferenceAnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {**reference_annotations.serialize(annotation), "summary": summary}


@router.get("/research-inference/{run_id}/volume-slice-corrections")
def list_volume_slice_corrections(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    verify_case_access(run.case_id, current_user, db, access="read")
    output = ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None
    if not output or output.get("type") != "volume_segmentation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VOLUME_RUN_REQUIRED: slice corrections belong to volumetric segmentation runs.")
    rows = db.query(ReferenceAnnotation).filter(ReferenceAnnotation.derived_from_run_id == run.id,
                                                ReferenceAnnotation.kind == reference_annotations.VOLUME_SLICE).all()
    return {"run_id": run.id, **reference_annotations.volume_corrections_summary(output, rows)}


@router.get("/uploads/{file_id}/reference-annotations")
def list_reference_annotations(file_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    file_record = _image_upload(db, file_id, current_user, "read")
    rows = db.query(ReferenceAnnotation).filter(ReferenceAnnotation.file_id == file_record.id).order_by(ReferenceAnnotation.id.desc()).all()
    return {"file_id": file_record.id, "annotations": [reference_annotations.serialize(row) for row in rows]}


@router.get("/research-inference/{run_id}/reference-comparison/{annotation_id}")
def compare_with_reference(run_id: int, annotation_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = db.get(InferenceRun, run_id)
    annotation = db.get(ReferenceAnnotation, annotation_id)
    if run is None or annotation is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run or reference annotation not found.")
    verify_case_access(run.case_id, current_user, db, access="read")
    if annotation.file_id != run.file_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="REFERENCE_FOR_ANOTHER_IMAGE: the reference is attached to a different upload.")
    output = ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None
    if output and "exif_orientation_applied" not in output and _exif_orientation(run.file) != 1:
        # Runs made before orientation handling used the stored (sideways or mirrored) pixel grid.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="RUN_ON_UNORIENTED_GRID: this run predates EXIF orientation handling and this image is stored rotated or mirrored; re-run the model.")
    try:
        return {"run_id": run.id, **reference_annotations.compare(output, annotation, run.id)}
    except reference_annotations.ReferenceAnnotationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/research-inference/{run_id}/agreement/{other_run_id}")
def compare_runs(run_id: int, other_run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Agreement between two research runs on the same upload; neither is treated as ground truth."""
    from app.services import run_agreement

    first, second = db.get(InferenceRun, run_id), db.get(InferenceRun, other_run_id)
    if first is None or second is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    verify_case_access(first.case_id, current_user, db, access="read")
    if second.file_id != first.file_id or second.case_id != first.case_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="RUNS_ON_DIFFERENT_UPLOADS: compare two runs of the same upload.")

    def output_of(run: InferenceRun):
        return ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None

    outputs = [output_of(first), output_of(second)]
    if any(output and output.get("type") in ("segmentation", "detection") and "exif_orientation_applied" not in output for output in outputs) \
            and _exif_orientation(first.file) != 1:
        # Runs made before orientation handling used the stored (sideways or mirrored) grid; pixels would not correspond.
        raise HTTPException(status_code=status.HTTP_409_CONFLICT,
                            detail="RUN_ON_UNORIENTED_GRID: a run predates EXIF orientation handling and this image is stored rotated or mirrored; re-run the model.")
    try:
        result = run_agreement.agreement(*outputs)
    except run_agreement.NotComparable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return {"run_ids": [first.id, second.id], "models": [first.model_name, second.model_name], **result}


@router.get("/research-inference/{run_id}/surfaces")
def get_volume_surfaces(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Patient-derived surfaces of a volumetric run's own mask, in the scan's voxel frame (not the atlas)."""
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    verify_case_access(run.case_id, current_user, db, access="read")
    output = ((run.findings[0].evidence_provenance or {}).get("output")) if run.findings else None
    if not output or output.get("type") != "volume_segmentation":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="VOLUME_RUN_REQUIRED: surfaces exist only for volumetric segmentation runs.")
    try:
        return {"run_id": run.id, **volume_inference.structure_surfaces(output)}
    except ImportError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=f"DEPENDENCY_MISSING: {exc.name or 'scikit-image'} is needed for surfaces (backend/requirements-ml.txt).")


class ChestRadiographRequest(BaseModel):
    """The requesting user states that the upload is a frontal chest radiograph."""

    attest_frontal_chest_radiograph: Literal[True]

    model_config = ConfigDict(extra="forbid")


@router.get("/chest-radiograph-model")
def get_chest_radiograph_model(current_user: User = Depends(get_current_user)):
    """The third-party chest-radiograph model: availability, publisher and weight hashes."""
    return cxr_research.model_card()


@router.post("/uploads/{file_id}/chest-radiograph-analysis", status_code=status.HTTP_201_CREATED)
def run_chest_radiograph_analysis(
    file_id: int,
    request: ChestRadiographRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Research analysis of a chest radiograph with TorchXRayVision's pretrained models
    (app.services.cxr_research). Not trained or evaluated by MedTwin; the output is a finding
    pending human review."""
    file_record = db.get(UploadedFile, file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, current_user, db)
    if file_record.modality != ModalityType.IMAGE or not file_record.filename.lower().endswith((".png", ".jpg", ".jpeg", ".bmp")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNSUPPORTED_INPUT: a PNG, JPEG or BMP image upload is required.")
    if not file_record.is_associated or file_record.withdrawn_at is not None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Withdrawn or unassociated uploads cannot enter case-level processing.")
    try:
        with upload_store.materialize(Path(file_record.file_path)) as plain:
            content_check = model_inference.check_document_photograph(plain)
        with model_inference._inference_lock:  # one research model on the GPU at a time
            run = cxr_research.execute(db, file_record, current_user, content_check)
    except model_inference.InferenceNotPermitted as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except cxr_research.CxrNotApplicable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"MODEL_INPUT_INCOMPATIBLE: {exc}")
    except cxr_research.CxrUnavailable as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return serialize_research_run(run)


class CtOrganRequest(BaseModel):
    """The requesting user states that the upload is a CT volume; fast uses the 3 mm model."""

    attest_ct_volume: Literal[True]
    fast: bool = True

    model_config = ConfigDict(extra="forbid")


@router.get("/ct-organ-model")
def get_ct_organ_model(current_user: User = Depends(get_current_user)):
    """The third-party CT organ model (TotalSegmentator): availability, publisher and the local external check."""
    return ct_organ_research.model_card()


@router.post("/uploads/{file_id}/ct-organ-segmentation", status_code=status.HTTP_201_CREATED,
             responses={202: {"description": "Queued for the background worker (worker execution mode)."}})
def run_ct_organ_segmentation(
    file_id: int,
    request: CtOrganRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Research segmentation of a CT volume with TotalSegmentator's published weights
    (app.services.ct_organ_research). Not trained by MedTwin; the output is a finding pending human review.
    Queued on the GPU slot like the other research models; refusals are typed before anything is queued."""
    file_record = db.get(UploadedFile, file_id)
    if file_record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found.")
    verify_case_access(file_record.case_id, current_user, db)
    if file_record.modality != ModalityType.IMAGE or not file_record.filename.lower().endswith((".nii", ".nii.gz")):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="UNSUPPORTED_INPUT: a NIfTI CT volume (.nii or .nii.gz) is required.")
    state = ct_organ_research.availability()
    if not state["available"] or not state.get("fast" if request.fast else "full_resolution"):
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                            detail=state.get("reason") or f"The {'fast' if request.fast else 'full-resolution'} TotalSegmentator weights are not installed.")
    try:
        ct_organ_research.check_upload(file_record)
    except ct_organ_research.CtNotApplicable as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"MODEL_INPUT_INCOMPATIBLE: {exc}")

    key = f"ct-organs:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(db, "CT_ORGAN_SEGMENTATION", payload={"fast": request.fast}, requested_by=current_user,
                                      case_id=file_record.case_id, file_id=file_record.id, resource="GPU", idempotency_key=key)
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
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="CT organ segmentation failed; the error state was recorded on the job.")


class SeriesInferenceRequest(BaseModel):
    upload_ids: list[int] = Field(..., min_length=2, max_length=2000)
    series_reference: Optional[str] = Field(default=None, pattern="^[0-9a-f]{16}$")
    model_id: str = Field(..., min_length=1, max_length=128)
    # Cardiac cine MRI (short-axis stack) or an abdominal CT series for the CT volume models.
    declared_input_type: Literal["MRI", "CT_ABDOMEN_VOLUME", "CT_CHEST_VOLUME", "HEAD_CT_SERIES"] = "MRI"
    phase: Optional[int] = Field(default=None, ge=0, le=1000)
    # The requester confirms the series is a short-axis cine stack at end-diastole or end-systole; tags cannot show it.
    short_axis_attested: bool = False

    model_config = ConfigDict(extra="forbid")


@router.post("/cases/{case_id}/dicom-series/research-inference", status_code=status.HTTP_201_CREATED,
             responses={202: {"description": "Queued for the background worker (worker execution mode)."}})
def run_series_research_inference(
    case_id: int,
    request: SeriesInferenceRequest,
    idempotency_key: Optional[str] = Header(default=None, alias="Idempotency-Key", max_length=128),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Run a volumetric research model on an assembled multi-file DICOM series. The series must
    assemble without issues and pass the same input checks as a NIfTI frame."""
    from app.routers.modalities import load_series, series_records

    verify_case_access(case_id, current_user, db)
    records = series_records(case_id, request.upload_ids, db)
    try:
        model = model_inference.get_model(request.model_id)
        report = load_series(records, request.series_reference, load_pixels=True, phase=request.phase)
        model_inference.prepare_series(model, report, request.declared_input_type, {"short_axis_attested": request.short_axis_attested})
    except model_inference.InferenceNotPermitted as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    first = db.get(UploadedFile, report["ordered_upload_ids"][0])
    key = f"research-series:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(
        db, "RESEARCH_SERIES_INFERENCE", requested_by=current_user, case_id=case_id, file_id=first.id, resource="GPU", idempotency_key=key,
        payload={"upload_ids": report["upload_ids"], "series_reference": report["series_reference"], "model_id": request.model_id,
                 "declared_input_type": request.declared_input_type, "phase": request.phase,
                 "short_axis_attested": request.short_axis_attested},
    )
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
    refusal = "InferenceNotPermitted: "
    if job.status == "FAILED" and (job.last_error or "").startswith(refusal):
        # A check that needs the network (slice applicability, axis convention, anatomy) refused the series.
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=job.last_error[len(refusal):])
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Research inference on the series failed; the error state was recorded in provenance.")


@router.get("/research-inference/{run_id}")
def get_research_inference(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    verify_case_access(run.case_id, current_user, db, access="read")
    finding_id = run.findings[0].id if run.findings else None
    return serialize_research_run(run, _latest_reviews(db, {finding_id} if finding_id else set()).get(finding_id))
