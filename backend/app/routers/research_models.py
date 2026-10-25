"""Research-only inference with registered MedTwin models.

Runs go through the durable job queue (GPU resource). Outputs stay labelled
RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED and pending human review; boxes and masks
are returned in the source image's pixel coordinates for overlay.
"""

from typing import Literal, Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Finding, InferenceRun, UploadedFile, User
from app.routers.jobs import serialize_analysis_job
from app.services import job_handlers  # noqa: F401 - registers the job handlers
from app.services import job_queue, model_inference
from app.services.auth import get_current_user, verify_case_access
from app.services.model_registry import RegistryConfigurationError

router = APIRouter(tags=["Research Models"])

NOTICE = ("Research-only models trained on public datasets and evaluated on internal held-out splits. "
          "Not clinically validated; outputs require human review and must not be used for diagnosis.")


class ResearchInferenceRequest(BaseModel):
    model_id: str = Field(min_length=1, max_length=128)
    declared_input_type: Literal["ENDOSCOPY", "ANGIOGRAPHY", "CT", "MICROSCOPY"]


def serialize_research_run(run: InferenceRun) -> dict:
    payload = serialize_analysis_job(run)
    finding: Optional[Finding] = run.findings[0] if run.findings else None
    provenance = (finding.evidence_provenance or {}) if finding else {}
    payload["research_output"] = provenance.get("output")
    payload["research_provenance"] = {key: value for key, value in provenance.items() if key != "output"}
    return payload


@router.get("/research-models")
def list_research_models(current_user: User = Depends(get_current_user)):
    try:
        models = model_inference.inference_models()
    except RegistryConfigurationError as exc:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
    return {"notice": NOTICE, "input_types": model_inference.MODALITY_LABELS, "models": models}


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
        model_inference.check_input(model, file_record, request.declared_input_type)
    except model_inference.InferenceNotPermitted as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    key = f"research:{current_user.id}:{idempotency_key}" if idempotency_key else None
    job, _created = job_queue.enqueue(
        db, "RESEARCH_MODEL_INFERENCE", payload={"model_id": request.model_id, "declared_input_type": request.declared_input_type},
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
    raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                        detail="Research inference failed; the error state was recorded in provenance.")


@router.get("/research-inference/{run_id}")
def get_research_inference(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    run = db.get(InferenceRun, run_id)
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Run not found.")
    verify_case_access(run.case_id, current_user, db, access="read")
    return serialize_research_run(run)
