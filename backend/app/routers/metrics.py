"""Validation-readiness and manuscript traceability endpoints.

The manifest below reports implementation state, not clinical performance. It
contains no fabricated benchmark values; measured results must come from saved,
reproducible evaluation artifacts before they can be surfaced here.

Equation numbers follow the earlier MedTwin_IEEE_Manuscript_Final.docx (Eq. 1-16).
The revised draft in the workspace numbers its equations 1-12; its claim-level
matrix is served by GET /research/traceability from docs/research/traceability.json.
"""

import hashlib
import json
import math
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database import get_db
from app.models.entities import Case, Finding, ForecastRecord, MultimodalFusionRecord, User
from app.services import model_registry
from app.services.auth import get_current_user

router = APIRouter(prefix="/metrics", tags=["Research Metrics & Validation"])

MAX_EVALUATION_REPORT_BYTES = 5 * 1024 * 1024
EXPERIMENT_METRICS = {
    "classification": (
        "accuracy",
        "balanced_accuracy",
        "macro_f1",
        "macro_auroc_one_vs_rest",
        "ece_uncalibrated",
        "ece_temperature_scaled",
        "brier_multiclass",
    ),
    "segmentation": (
        "mean_foreground_dice_per_image",
        "macro_segment_dice",
        "vessel_dice",
        "vessel_iou",
        "vessel_hd95_px_at_model_resolution",
    ),
    "detection": (
        "map_50_95",
        "ap_50",
        "ap_75",
        "ap_small",
        "ap_medium",
        "ap_large",
        "ar_1",
        "ar_10",
        "ar_100",
    ),
}


class _ExperimentReportError(Exception):
    def __init__(self, code: str, reason: str):
        super().__init__(reason)
        self.code = code
        self.reason = reason


def _task_family(task: Any) -> str | None:
    value = str(task or "").lower()
    if "classification" in value:
        return "classification"
    if "segmentation" in value:
        return "segmentation"
    if "detection" in value:
        return "detection"
    return None


def _finite_number(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value if math.isfinite(value) else None


def _short_text(value: Any, limit: int = 500) -> str | None:
    if not isinstance(value, str):
        return None
    cleaned = " ".join(value.split())
    return cleaned[:limit] if cleaned else None


def _safe_report_path(registered_path: Any) -> Path:
    if not isinstance(registered_path, str) or not registered_path.strip():
        raise _ExperimentReportError("EVALUATION_REPORT_NOT_REGISTERED", "No evaluation report is registered.")
    try:
        registered = Path(registered_path)
    except (OSError, ValueError) as exc:
        raise _ExperimentReportError("EVALUATION_REPORT_PATH_INVALID", "The registered evaluation report path is invalid.") from exc
    if registered.suffix.lower() != ".json":
        raise _ExperimentReportError("EVALUATION_REPORT_NOT_JSON", "The registered evaluation report is not JSON.")
    try:
        root = model_registry.PROJECT_ROOT.resolve()
        candidate = model_registry._resolve_artifact_path(registered_path).resolve()
    except (OSError, RuntimeError, ValueError) as exc:
        raise _ExperimentReportError("EVALUATION_REPORT_PATH_INVALID", "The registered evaluation report path cannot be resolved safely.") from exc
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise _ExperimentReportError(
            "EVALUATION_REPORT_OUTSIDE_PROJECT_ROOT",
            "The registered evaluation report resolves outside the project artifact root.",
        ) from exc
    try:
        if not candidate.is_file():
            raise _ExperimentReportError("EVALUATION_REPORT_MISSING", "The registered evaluation report file is missing.")
        if candidate.stat().st_size > MAX_EVALUATION_REPORT_BYTES:
            raise _ExperimentReportError("EVALUATION_REPORT_TOO_LARGE", "The registered evaluation report exceeds the safe read limit.")
    except _ExperimentReportError:
        raise
    except OSError as exc:
        raise _ExperimentReportError("EVALUATION_REPORT_UNREADABLE", "The registered evaluation report cannot be inspected safely.") from exc
    return candidate


def _confidence_intervals(
    report: dict[str, Any],
    source: dict[str, Any],
    metric_names: tuple[str, ...],
    family: str,
) -> dict[str, dict[str, Any]]:
    raw = report.get("confidence_intervals_95") if family == "classification" else source.get("confidence_intervals_95")
    if not isinstance(raw, dict):
        return {}
    intervals: dict[str, dict[str, Any]] = {}
    for name in metric_names:
        interval = raw.get(name)
        if not isinstance(interval, dict):
            continue
        low, high = _finite_number(interval.get("low")), _finite_number(interval.get("high"))
        if low is None or high is None:
            continue
        intervals[name] = {
            "low": low,
            "high": high,
            "status": _short_text(interval.get("status"), 64) or "COMPUTED",
        }
    return intervals


def _load_experiment(model: dict[str, Any], family: str) -> dict[str, Any]:
    bundle = model.get("artifact_bundle")
    if not isinstance(bundle, dict):
        raise _ExperimentReportError("ARTIFACT_BUNDLE_INVALID", "The registry artifact bundle is invalid.")
    registered_path = bundle.get("evaluation_report_path")
    path = _safe_report_path(registered_path)
    try:
        report_bytes = path.read_bytes()
        report = json.loads(report_bytes.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise _ExperimentReportError("EVALUATION_REPORT_INVALID_JSON", "The registered evaluation report could not be decoded safely.") from exc
    if not isinstance(report, dict):
        raise _ExperimentReportError("EVALUATION_REPORT_SCHEMA_INVALID", "The evaluation report root must be an object.")

    model_id = model.get("model_id")
    if report.get("model_id") != model_id:
        raise _ExperimentReportError("EVALUATION_REPORT_MODEL_MISMATCH", "The evaluation report model id does not match the registry.")
    if report.get("dataset_version") != bundle.get("dataset_version"):
        raise _ExperimentReportError("EVALUATION_REPORT_DATASET_MISMATCH", "The evaluation report dataset version does not match the registry.")
    report_checkpoint = report.get("checkpoint")
    registered_checkpoint = bundle.get("checkpoint_sha256")
    if not isinstance(report_checkpoint, dict) or report_checkpoint.get("sha256") != registered_checkpoint:
        raise _ExperimentReportError("EVALUATION_REPORT_CHECKPOINT_MISMATCH", "The evaluation report checkpoint does not match the registry.")

    if family == "classification":
        sample_count = report.get("test_n")
        source = report.get("metrics")
    else:
        test = report.get("test")
        sample_count = test.get("n_images") if isinstance(test, dict) else None
        source = test.get("metrics") if family == "detection" and isinstance(test, dict) else test
    if isinstance(sample_count, bool) or not isinstance(sample_count, int) or sample_count <= 0 or not isinstance(source, dict):
        raise _ExperimentReportError("EVALUATION_REPORT_SCHEMA_INVALID", "The evaluation report has no valid held-out sample summary.")

    metric_names = EXPERIMENT_METRICS[family]
    metrics = {name: number for name in metric_names if (number := _finite_number(source.get(name))) is not None}
    if not metrics:
        raise _ExperimentReportError("EVALUATION_REPORT_METRICS_INVALID", "The evaluation report has no recognised finite headline metrics.")
    raw_limitations = report.get("limitations")
    if not isinstance(raw_limitations, list):
        raw_limitations = []
    limitations = [text for item in raw_limitations if (text := _short_text(item)) is not None][:8]
    limitations.append("Internal held-out research experiment only; not external or clinical validation.")
    try:
        artifact = path.relative_to(model_registry.PROJECT_ROOT.resolve()).as_posix()
    except ValueError:  # guarded by _safe_report_path; retained as a non-leaking fallback
        artifact = path.name
    return {
        "model_id": model_id,
        "display_name": _short_text(model.get("display_name"), 200) or str(model_id),
        "task": model.get("task"),
        "registry_status": model.get("status"),
        "research_inference": model.get("research_inference") is True,
        "dataset": _short_text(report.get("dataset"), 200),
        "dataset_version": bundle.get("dataset_version"),
        "dataset_license": _short_text(bundle.get("dataset_license"), 300),
        "split_method": _short_text(report.get("split_method"), 300),
        "held_out_sample_count": sample_count,
        "metrics": metrics,
        "confidence_intervals_95": _confidence_intervals(report, source, metric_names, family),
        "evaluation_protocol": _short_text(report.get("evaluation_protocol"), 1000),
        "evaluation_report": artifact,
        "evaluation_report_sha256": hashlib.sha256(report_bytes).hexdigest(),
        "evidence_scope": "INTERNAL_HELD_OUT_RESEARCH_ONLY",
        "external_validation": False,
        "clinical_validation": False,
        "limitations": limitations,
    }


def _registered_experiment_evidence(family: str) -> Dict[str, Any]:
    try:
        models = model_registry._load_registry().get("models", [])
    except model_registry.RegistryConfigurationError:
        return {
            **_not_run("The model registry could not be loaded safely; no experiment metric is surfaced."),
            "registered_models_considered": 0,
            "unavailable_reports": [{"code": "MODEL_REGISTRY_INVALID"}],
        }
    matching = [model for model in models if _task_family(model.get("task")) == family]
    experiments: list[dict[str, Any]] = []
    unavailable: list[dict[str, Any]] = []
    for model in matching:
        try:
            experiments.append(_load_experiment(model, family))
        except _ExperimentReportError as exc:
            unavailable.append({
                "model_id": model.get("model_id"),
                "task": model.get("task"),
                "code": exc.code,
                "reason": exc.reason,
            })
    if not experiments:
        return {
            **_not_run(
                f"No readable, provenance-matched registered {family} held-out evaluation report was found; "
                "no performance estimate is surfaced."
            ),
            "registered_models_considered": len(matching),
            "unavailable_reports": unavailable,
        }
    return {
        "status": "COMPLETED",
        "value": {
            "experiment_count": len(experiments),
            "evidence_scope": "INTERNAL_HELD_OUT_RESEARCH_ONLY",
            "external_validation": False,
            "clinical_validation": False,
            "experiments": experiments,
        },
        "reason": (
            "Metrics were loaded from provenance-matched registered evaluation reports. "
            "They describe internal held-out research experiments, not external or clinical validation."
        ),
        "registered_models_considered": len(matching),
        "unavailable_reports": unavailable,
    }


def _not_run(reason: str) -> Dict[str, Any]:
    return {"status": "NOT_RUN", "value": None, "reason": reason}


def _latest_software_benchmark() -> Dict[str, Any]:
    """Load a completed local-serving artifact without treating it as model validation."""
    results_dir = Path(__file__).resolve().parents[3] / "benchmarks" / "results"
    for artifact in sorted(results_dir.glob("http-benchmark-*.json"), reverse=True):
        try:
            payload_bytes = artifact.read_bytes()
            payload = json.loads(payload_bytes)
        except (OSError, json.JSONDecodeError):
            continue
        if payload.get("status") != "completed" or payload.get("clinical_performance_measured") is not False:
            continue
        profiles = {
            str(profile.get("concurrency")): profile.get("aggregate", {})
            for profile in payload.get("profiles", [])
        }
        return {
            "status": "COMPLETED",
            "value": {
                "benchmark_kind": payload.get("benchmark_kind"),
                "endpoint": payload.get("workload", {}).get("path"),
                "generated_at_utc": payload.get("generated_at_utc"),
                "profiles": profiles,
                "artifact": str(artifact.relative_to(Path(__file__).resolve().parents[3])),
                "artifact_sha256": hashlib.sha256(payload_bytes).hexdigest(),
            },
            "reason": "Same-host HTTP-serving measurement only; no model inference or clinical performance was measured.",
        }
    return _not_run("No completed timestamped software-serving benchmark artifact was found.")


@router.get("/ieee-validation")
def get_ieee_validation_metrics(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)) -> Dict[str, Any]:
    """Return an honest code-to-equation map and explicit validation gaps."""
    software_benchmark = _latest_software_benchmark()
    classification_evidence = _registered_experiment_evidence("classification")
    segmentation_evidence = _registered_experiment_evidence("segmentation")
    detection_evidence = _registered_experiment_evidence("detection")
    equations_manifest: List[Dict[str, Any]] = [
        {
            "equation_id": "Eq. 1-2",
            "title": "Classification probabilities and cross-entropy",
            "implementation_module": "backend/app/services/model_inference.py",
            "status": "INTERNAL_HELD_OUT_RESEARCH_EVIDENCE" if classification_evidence["status"] == "COMPLETED" else "NO_REGISTERED_EXPERIMENT",
            "evaluation_type": "INTERNAL_HELD_OUT_RESEARCH_ONLY" if classification_evidence["status"] == "COMPLETED" else "NOT_RUN",
            "measured_metric": classification_evidence,
        },
        {
            "equation_id": "Eq. 3-4",
            "title": "Segmentation losses and Dice / IoU",
            "implementation_module": "backend/app/services/evaluation_metrics.py",
            "status": "INTERNAL_HELD_OUT_RESEARCH_EVIDENCE" if segmentation_evidence["status"] == "COMPLETED" else "EVALUATION_METRICS_IMPLEMENTED_NO_REGISTERED_EXPERIMENT",
            "evaluation_type": "INTERNAL_HELD_OUT_RESEARCH_ONLY" if segmentation_evidence["status"] == "COMPLETED" else "CODE_LEVEL_ONLY",
            "measured_metric": segmentation_evidence,
        },
        {
            "equation_id": "Eq. 5",
            "title": "Object-detection objective",
            "implementation_module": "backend/app/services/evaluation_metrics.py",
            "status": "INTERNAL_HELD_OUT_RESEARCH_EVIDENCE" if detection_evidence["status"] == "COMPLETED" else "EVALUATION_METRICS_IMPLEMENTED_NO_REGISTERED_EXPERIMENT",
            "evaluation_type": "INTERNAL_HELD_OUT_RESEARCH_ONLY" if detection_evidence["status"] == "COMPLETED" else "CODE_LEVEL_ONLY",
            "measured_metric": detection_evidence,
        },
        {
            "equation_id": "Eq. 6",
            "title": "ECG class-weighted loss",
            "implementation_module": "backend/app/services/ecg_processor.py",
            "status": "MODEL_UNAVAILABLE",
            "evaluation_type": "NOT_RUN",
            "measured_metric": _not_run("The ECG path validates files and renders previews only; no PTB-XL/MIT-BIH model was evaluated."),
        },
        {
            "equation_id": "Eq. 7",
            "title": "Clinical NLP entity extraction",
            "implementation_module": "backend/app/services/nlp_processor.py",
            "status": "RULE_BASELINE_UNIT_TESTED",
            "evaluation_type": "NOT_RUN",
            "measured_metric": _not_run("Context rules (rules-v2.0.0) are unit-tested; no annotated entity, negation, and temporality corpus evaluation has been run."),
        },
        {
            "equation_id": "Eq. 8-10",
            "title": "Masked gated multimodal fusion",
            "implementation_module": "backend/app/services/fusion_service.py",
            "status": "IMPLEMENTED_UNIT_TESTED_DATA_GATE_ACTIVE",
            "evaluation_type": "CODE_LEVEL_ONLY",
            "measured_metric": _not_run("Tensor invariants are unit-tested, but case-level fusion requires genuinely paired data and validated encoders."),
        },
        {
            "equation_id": "Eq. 11-12",
            "title": "Rigid registration and held-out TRE gate",
            "implementation_module": "backend/app/services/registration_service.py",
            "status": "IMPLEMENTED_UNIT_TESTED_SYNTHETIC_FIXTURES",
            "evaluation_type": "CODE_LEVEL_ONLY",
            "measured_metric": _not_run("No patient landmarks or held-out clinical registration benchmark are configured."),
        },
        {
            "equation_id": "Eq. 13-14",
            "title": "Longitudinal forecasting and error evaluation",
            "implementation_module": "backend/app/services/forecasting_service.py",
            "status": "ELIGIBILITY_GATE_ONLY_NO_VALIDATED_MODEL",
            "evaluation_type": "NOT_RUN",
            "measured_metric": _not_run("The data gate is enforced and MAE/RMSE scoring of uploaded forecasts is tested; no forecaster has been evaluated, so no forecast is produced."),
        },
        {
            "equation_id": "Eq. 15",
            "title": "Probability calibration",
            "implementation_module": "backend/app/services/calibration_service.py",
            "status": "UTILITY_IMPLEMENTED_UNIT_TESTED",
            "evaluation_type": "CODE_LEVEL_ONLY",
            "measured_metric": _not_run("Calibration utilities are tested, but no validated model probabilities and labels are available."),
        },
        {
            "equation_id": "Eq. 16",
            "title": "Measured service latency",
            "implementation_module": "benchmarks/http_benchmark.py",
            "status": "SOFTWARE_BENCHMARK_COMPLETED" if software_benchmark["status"] == "COMPLETED" else "SOFTWARE_BENCHMARK_NOT_RUN",
            "evaluation_type": "REPRODUCIBLE_LOCAL_ARTIFACT",
            "measured_metric": software_benchmark,
        },
    ]

    return {
        "status": "PENDING_VALIDATION",
        "manuscript": "MedTwin_IEEE_Manuscript_Final.docx (earlier version; see /research/traceability for the revised draft)",
        "framework": "MedTwin multimodal clinical evidence research prototype",
        "equations_tracked": len(equations_manifest),
        "equations_with_code_paths": sum(1 for eq in equations_manifest if eq["implementation_module"]),
        "database_records": {
            "cases_count": db.query(Case).count(),
            "findings_count": db.query(Finding).count(),
            "fusion_evaluations_count": db.query(MultimodalFusionRecord).count(),
            "forecast_evaluations_count": db.query(ForecastRecord).count(),
        },
        "equations": equations_manifest,
        "research_notice": (
            "NOTICE: This is a code-readiness manifest, not a clinical-performance report. "
            "Registered classification, segmentation, and detection reports are surfaced only as internal held-out research evidence; "
            "they are not external or clinical validation. MURA, ECG, clinical-text, paired-fusion, registration, forecasting, and "
            "clinical calibration results remain pending."
        ),
    }
