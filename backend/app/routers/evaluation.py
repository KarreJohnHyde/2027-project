"""Validation Center: metrics over uploaded held-out predictions.

Every run records its claimed dataset, version, split, frozen checkpoint and
code commit (manuscript Sec. X). A run is eligible for research reporting only
when those identifiers resolve exactly across the local model registry,
checkpoint bytes, registered evaluation report and dataset-task audit, and the
uploaded evaluator bytes match the registered held-out input artifact. All
other runs are retained as EXPLORATORY. This gate never activates a model for
clinical use. Uncommitted code changes are a reproducibility warning.
"""

from __future__ import annotations

import hashlib
from typing import Literal, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import EvaluationRun, User, UserRole
from app.services.audit_service import log_audit_event
from app.services.auth import get_current_user
from app.services.clinical_nlp_evaluation import SCHEMA_VERSION as CLINICAL_NLP_SCHEMA_VERSION
from app.services.clinical_nlp_evaluation import evaluate_clinical_nlp
from app.services.evaluation_context import (
    COMBINED_INPUT_DIGEST_SCHEME,
    RAW_INPUT_DIGEST_SCHEME,
    resolve_evaluation_context,
)
from app.services.ocr_evaluation import SCHEMA_VERSION as OCR_SCHEMA_VERSION
from app.services.ocr_evaluation import evaluate_ocr
from app.services.evaluation_metrics import (
    DEFAULT_BOOTSTRAP,
    DEFAULT_SEED,
    EvaluationInputError,
    evaluate_classification,
    evaluate_detection,
    evaluate_forecast,
    evaluate_lab_extraction,
    evaluate_multiclass,
    evaluate_regression,
    evaluate_segmentation,
    evaluate_segmentation_batch,
    evaluate_survival,
)

router = APIRouter(prefix="/evaluation", tags=["Validation Center"])
MAX_PREDICTION_BYTES = 20 * 1024 * 1024
MAX_ARCHIVE_BYTES = 200 * 1024 * 1024
Split = Literal["test", "external_test", "validation", "development"]


async def _read(upload: UploadFile, limit: int = MAX_PREDICTION_BYTES) -> bytes:
    content = await upload.read(limit + 1)
    if len(content) > limit:
        raise HTTPException(status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail=f"File exceeds {limit // (1024 * 1024)} MB.")
    if not content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File is empty.")
    return content


def _context(
    task: str,
    model_id: Optional[str],
    dataset_label: Optional[str],
    dataset_version: Optional[str],
    split: Optional[str],
    checkpoint: Optional[str],
    input_sha256: str,
    input_digest_scheme: str,
) -> dict:
    return resolve_evaluation_context(
        task,
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_sha256,
        input_digest_scheme,
    )


def _persist(db: Session, user: User, task: str, filename: str, digest: str, result: dict, config: dict, context: dict) -> dict:
    result = {**result, "evaluation_context": context}
    run = EvaluationRun(
        task_type=task, model_id=context["model_id"], dataset_label=context["dataset"], input_filename=filename[:256], input_sha256=digest,
        n_samples=int(result.get("n", 0)), n_groups=result.get("n_groups"), config={**config, **context}, metrics=result, created_by_id=user.id,
    )
    db.add(run)
    db.commit()
    db.refresh(run)
    log_audit_event(db=db, action="EVALUATION_RUN_RECORDED", resource_type="EVALUATION_RUN", resource_id=str(run.id), user=user,
                    details={"task_type": task, "input_sha256": digest, "n": run.n_samples, "reporting_status": context["reporting_status"]})
    return {"run_id": run.id, "input_sha256": digest, "created_at": run.created_at.isoformat(), **result}


def _combined_digest(*parts: bytes) -> str:
    return hashlib.sha256(b"".join(hashlib.sha256(part).digest() for part in parts)).hexdigest()


def _stored_context(run: EvaluationRun) -> dict:
    """Fail closed when reading runs created before immutable input binding."""
    raw = run.metrics.get("evaluation_context") if isinstance(run.metrics, dict) else None
    context = dict(raw) if isinstance(raw, dict) else {}
    if context.get("reporting_status") != "ELIGIBLE_FOR_REPORTING":
        context.setdefault("reporting_status", "EXPLORATORY")
        return context
    resolution = context.get("registry_resolution")
    input_digest = context.get("evaluation_input_sha256")
    binding_is_recorded = (
        isinstance(resolution, dict)
        and isinstance(input_digest, str)
        and input_digest == run.input_sha256
        and resolution.get("evaluation_input_sha256") == input_digest
        and resolution.get("evaluation_input_artifact_verified") is True
        and resolution.get("exact_match") is True
    )
    if not binding_is_recorded:
        context["reporting_status"] = "EXPLORATORY"
        blockers = list(context.get("reporting_blockers") or [])
        if "evaluation_input_binding_not_recorded" not in blockers:
            blockers.append("evaluation_input_binding_not_recorded")
        context["reporting_blockers"] = blockers
    return context


@router.post("/clinical_nlp")
async def run_clinical_nlp_evaluation(
    gold: UploadFile = File(...),
    predictions: UploadFile = File(...),
    deidentified: bool = Form(...),
    independently_annotated: bool = Form(...),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Score independently supplied gold and predicted clinical entity-span JSON.

    The schema records document IDs, character counts, zero-based/exclusive
    offsets, normalized labels, assertion, negation and temporality. Metrics stay
    exploratory unless the standard dataset/version/held-out/checkpoint context
    gate is satisfied.
    """
    if not deidentified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Clinical NLP evaluation accepts de-identified research artifacts only.",
        )
    if not independently_annotated:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Gold spans must be independently annotated; model-generated pseudo-labels are not accepted as gold.",
        )
    gold_content = await _read(gold)
    prediction_content = await _read(predictions)
    try:
        result = evaluate_clinical_nlp(gold_content, prediction_content)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    gold_digest = hashlib.sha256(gold_content).hexdigest()
    prediction_digest = hashlib.sha256(prediction_content).hexdigest()
    result["input_artifacts"] = {
        "gold": {"role": "gold", "sha256": gold_digest},
        "predictions": {"role": "prediction", "sha256": prediction_digest},
    }
    input_digest = _combined_digest(gold_content, prediction_content)
    context = _context(
        "clinical_nlp",
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        COMBINED_INPUT_DIGEST_SCHEME,
    )
    if result["gold_span_count"] == 0:
        context["reporting_status"] = "EXPLORATORY"
        context["reporting_blockers"].append("nonempty_gold_standard")
    config = {
        "schema_version": CLINICAL_NLP_SCHEMA_VERSION,
        "matching": "exact_span_and_maximum_cardinality_label_aware_overlap",
        "deidentified_attested": True,
        "independently_annotated_attested": True,
    }
    return _persist(
        db,
        current_user,
        "clinical_nlp",
        "gold.json|predictions.json",
        input_digest,
        result,
        config,
        context,
    )


@router.post("/ocr")
async def run_ocr_evaluation(
    gold: UploadFile = File(...),
    predictions: UploadFile = File(...),
    deidentified: bool = Form(...),
    independently_transcribed: bool = Form(...),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Measure CER/WER against independent page transcriptions without retaining text."""
    if not deidentified:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OCR evaluation accepts de-identified research artifacts only.",
        )
    if not independently_transcribed:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="OCR gold text must be independently transcribed from the source page.",
        )
    gold_content = await _read(gold)
    prediction_content = await _read(predictions)
    try:
        result = evaluate_ocr(gold_content, prediction_content)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    result["input_artifacts"] = {
        "gold": {"role": "gold", "sha256": hashlib.sha256(gold_content).hexdigest()},
        "predictions": {"role": "prediction", "sha256": hashlib.sha256(prediction_content).hexdigest()},
    }
    input_digest = _combined_digest(gold_content, prediction_content)
    context = _context(
        "ocr",
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        COMBINED_INPUT_DIGEST_SCHEME,
    )
    config = {
        "schema_version": OCR_SCHEMA_VERSION,
        "deidentified_attested": True,
        "independently_transcribed_attested": True,
        "normalization": result["normalization"],
    }
    return _persist(
        db,
        current_user,
        "ocr",
        "gold.json|predictions.json",
        input_digest,
        result,
        config,
        context,
    )


@router.post("/{task}")
async def run_tabular_evaluation(
    task: Literal["classification", "multiclass", "regression", "survival", "forecast", "lab_extraction"],
    file: UploadFile = File(...),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    threshold: Optional[float] = Form(None),
    alpha: Optional[float] = Form(None),
    abs_tolerance: float = Form(0.0),
    bootstrap: int = Form(DEFAULT_BOOTSTRAP),
    seed: int = Form(DEFAULT_SEED),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """CSV columns: classification y_true,y_score (or score)[,group_id or patient_id]; multiclass y_true,y_pred;
    regression y_true,y_pred[,lower,upper,group_id]; survival time,event,risk_score[,group_id];
    forecast patient_id,target,horizon,y_true,y_pred; lab_extraction patient_id,source_id,analyte_code,
    reference_value,predicted_value,reference_unit,predicted_unit."""
    if not 100 <= bootstrap <= 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bootstrap must be between 100 and 5000.")
    content = await _read(file)
    try:
        if task == "classification":
            result = evaluate_classification(content, threshold=threshold, rounds=bootstrap, seed=seed)
        elif task == "multiclass":
            result = evaluate_multiclass(content)
        elif task == "regression":
            result = evaluate_regression(content, alpha=alpha, rounds=bootstrap, seed=seed)
        elif task == "forecast":
            result = evaluate_forecast(content, rounds=bootstrap, seed=seed)
        elif task == "lab_extraction":
            result = evaluate_lab_extraction(content, abs_tolerance=abs_tolerance)
        else:
            result = evaluate_survival(content, rounds=bootstrap, seed=seed)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    config = {"threshold": threshold, "alpha": alpha, "abs_tolerance": abs_tolerance, "bootstrap": bootstrap, "seed": seed}
    input_digest = hashlib.sha256(content).hexdigest()
    context = _context(
        task,
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        RAW_INPUT_DIGEST_SCHEME,
    )
    return _persist(db, current_user, task, file.filename or "predictions.csv", input_digest, result, config, context)


@router.post("/segmentation/masks")
async def run_segmentation_evaluation(
    reference: UploadFile = File(...),
    prediction: UploadFile = File(...),
    spacing_x: float = Form(1.0, gt=0),
    spacing_y: float = Form(1.0, gt=0),
    unit: str = Form("px", max_length=8),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    reference_bytes = await _read(reference)
    prediction_bytes = await _read(prediction)
    try:
        result = evaluate_segmentation(reference_bytes, prediction_bytes, (spacing_x, spacing_y), unit)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    input_digest = _combined_digest(reference_bytes, prediction_bytes)
    context = _context(
        "segmentation",
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        COMBINED_INPUT_DIGEST_SCHEME,
    )
    return _persist(db, current_user, "segmentation", f"{reference.filename}|{prediction.filename}", input_digest, result, {"spacing": [spacing_x, spacing_y], "unit": unit}, context)


@router.post("/segmentation/batch")
async def run_segmentation_batch_evaluation(
    archive: UploadFile = File(...),
    spacing_x: float = Form(1.0, gt=0),
    spacing_y: float = Form(1.0, gt=0),
    unit: str = Form("px", max_length=8),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    bootstrap: int = Form(DEFAULT_BOOTSTRAP),
    seed: int = Form(DEFAULT_SEED),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """ZIP with manifest.csv (patient_id,reference_mask,predicted_mask) and the masks it lists."""
    if not 100 <= bootstrap <= 5000:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="bootstrap must be between 100 and 5000.")
    content = await _read(archive, MAX_ARCHIVE_BYTES)
    try:
        result = evaluate_segmentation_batch(content, (spacing_x, spacing_y), unit, rounds=bootstrap, seed=seed)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    input_digest = hashlib.sha256(content).hexdigest()
    context = _context(
        "segmentation_batch",
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        RAW_INPUT_DIGEST_SCHEME,
    )
    config = {"spacing": [spacing_x, spacing_y], "unit": unit, "bootstrap": bootstrap, "seed": seed}
    return _persist(db, current_user, "segmentation_batch", archive.filename or "masks.zip", input_digest, result, config, context)


@router.post("/detection/coco")
async def run_detection_evaluation(
    predictions: UploadFile = File(...),
    annotations: UploadFile = File(...),
    model_id: Optional[str] = Form(None),
    dataset_label: Optional[str] = Form(None),
    dataset_version: Optional[str] = Form(None),
    split: Optional[Split] = Form(None),
    checkpoint: Optional[str] = Form(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """COCO results JSON (predictions) against COCO reference annotations JSON."""
    prediction_bytes = await _read(predictions)
    annotation_bytes = await _read(annotations)
    try:
        result = evaluate_detection(prediction_bytes, annotation_bytes)
    except EvaluationInputError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc))
    if result.get("status") == "DEPENDENCY_MISSING":
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=result["reason"])
    input_digest = _combined_digest(prediction_bytes, annotation_bytes)
    context = _context(
        "detection",
        model_id,
        dataset_label,
        dataset_version,
        split,
        checkpoint,
        input_digest,
        COMBINED_INPUT_DIGEST_SCHEME,
    )
    return _persist(db, current_user, "detection", f"{predictions.filename}|{annotations.filename}", input_digest, result, {"protocol": "COCOeval bbox"}, context)


@router.get("/runs")
def list_evaluation_runs(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(EvaluationRun)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(EvaluationRun.created_by_id == current_user.id)
    runs = query.order_by(EvaluationRun.created_at.desc()).limit(100).all()
    response = []
    for run in runs:
        context = _stored_context(run)
        response.append(
            {"run_id": run.id, "task_type": run.task_type, "model_id": run.model_id, "dataset_label": run.dataset_label, "input_filename": run.input_filename,
             "input_sha256": run.input_sha256, "n_samples": run.n_samples, "created_at": run.created_at.isoformat(),
             "reporting_status": context["reporting_status"], "metrics": run.metrics.get("metrics")}
        )
    return response


@router.get("/runs/{run_id}")
def get_evaluation_run(run_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    query = db.query(EvaluationRun).filter(EvaluationRun.id == run_id)
    if current_user.role != UserRole.ADMIN:
        query = query.filter(EvaluationRun.created_by_id == current_user.id)
    run = query.first()
    if run is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Evaluation run not found.")
    context = _stored_context(run)
    metrics = {**run.metrics, "evaluation_context": context}
    config = {**run.config, "reporting_status": context["reporting_status"], "reporting_blockers": context.get("reporting_blockers", [])}
    return {"run_id": run.id, "task_type": run.task_type, "model_id": run.model_id, "dataset_label": run.dataset_label, "input_filename": run.input_filename,
            "input_sha256": run.input_sha256, "config": config, "created_at": run.created_at.isoformat(), **metrics}
