"""Registry-backed provenance gate for Validation Center runs.

``ELIGIBLE_FOR_REPORTING`` is deliberately narrow: it means that a research
evaluation run is bound to one locally registered model checkpoint and one
locally audited held-out dataset task, and the uploaded evaluator bytes match
the registered held-out input artifact. It never activates a model for
clinical use and it is not a claim of external or clinical validation.
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any, Optional

from app.services.build_info import code_revision
from app.services.dataset_registry import (
    DatasetTaskAuditUnavailableError,
    load_dataset_task_audit,
)
from app.services.model_registry import (
    RegistryConfigurationError,
    _load_registry,
    _resolve_artifact_path,
    _sha256,
)


REPORTABLE_SPLITS = {"test", "external_test"}
CHECKPOINT_SHA256 = re.compile(r"sha256:([0-9a-f]{64})\Z")
BARE_SHA256 = re.compile(r"[0-9a-f]{64}\Z")
ZERO_SHA256 = "0" * 64
REPORTING_SCOPE = "RESEARCH_EVIDENCE_ONLY_NOT_CLINICAL_ACTIVATION"
RAW_INPUT_DIGEST_SCHEME = "SHA256_RAW_BYTES_V1"
COMBINED_INPUT_DIGEST_SCHEME = "SHA256_ORDERED_PART_DIGESTS_V1"

_MODEL_TASKS: dict[str, set[str]] = {
    "classification": {"image_classification"},
    "multiclass": {"image_classification"},
    "detection": {"object_detection"},
    "segmentation": {"semantic_segmentation"},
    "segmentation_batch": {"semantic_segmentation"},
    "survival": {"survival_prediction"},
    "forecast": {"forecast"},
    "regression": {"regression"},
    "lab_extraction": {"lab_extraction"},
    "clinical_nlp": {"clinical_nlp"},
    "ocr": {"ocr"},
}

_DATASET_TASK_MARKERS: dict[str, tuple[str, ...]] = {
    "classification": ("CLASSIFICATION",),
    "multiclass": ("CLASSIFICATION",),
    "detection": ("DETECTION",),
    "segmentation": ("SEGMENTATION",),
    "segmentation_batch": ("SEGMENTATION",),
    "survival": ("SURVIVAL",),
    "forecast": ("FORECAST",),
    "regression": ("REGRESSION",),
    "lab_extraction": ("LAB", "EXTRACTION"),
    "clinical_nlp": ("CLINICAL_NLP", "NER", "ENTITY", "TEXT"),
    "ocr": ("OCR", "TEXT"),
}


def _text(value: Optional[str]) -> Optional[str]:
    normalized = (value or "").strip()
    return normalized or None


def _add(blockers: list[str], blocker: str) -> None:
    if blocker not in blockers:
        blockers.append(blocker)


@lru_cache(maxsize=32)
def _artifact_digest(path: str, size: int, mtime_ns: int) -> str:
    """Hash immutable artifact bytes, caching only for the same file state."""
    del size, mtime_ns
    return _sha256(Path(path))


def _read_model_report(
    model: dict[str, Any], blockers: list[str]
) -> dict[str, Any] | None:
    bundle = model.get("artifact_bundle") or {}
    report_name = bundle.get("evaluation_report_path")
    if not isinstance(report_name, str) or not report_name.strip():
        _add(blockers, "model_evaluation_report_missing")
        return None
    report_path = _resolve_artifact_path(report_name)
    if not report_path.is_file():
        _add(blockers, "model_evaluation_report_missing")
        return None
    try:
        report = json.loads(report_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError):
        _add(blockers, "model_evaluation_report_invalid")
        return None
    if not isinstance(report, dict):
        _add(blockers, "model_evaluation_report_invalid")
        return None

    if report.get("model_id") != model.get("model_id"):
        _add(blockers, "model_evaluation_report_model_mismatch")
    if report.get("dataset_version") != bundle.get("dataset_version"):
        _add(blockers, "model_evaluation_report_dataset_mismatch")
    report_checkpoint = report.get("checkpoint")
    if (
        not isinstance(report_checkpoint, dict)
        or report_checkpoint.get("sha256") != bundle.get("checkpoint_sha256")
    ):
        _add(blockers, "model_evaluation_report_checkpoint_mismatch")
    if not isinstance(report.get("dataset_id"), str) or not isinstance(
        report.get("task_id"), str
    ):
        _add(blockers, "model_evaluation_report_task_binding_missing")
    return report


def _resolve_evaluation_input(
    model: dict[str, Any],
    model_report: dict[str, Any] | None,
    evaluation_task: str,
    split: Optional[str],
    supplied_digest: str | None,
    supplied_digest_scheme: Optional[str],
    blockers: list[str],
    resolution: dict[str, Any],
) -> dict[str, Any] | None:
    """Verify that uploaded evaluator bytes are the registered held-out artifact."""
    bundle = model.get("artifact_bundle")
    if not isinstance(bundle, dict):
        bundle = {}
    binding = bundle.get("evaluation_input")
    if not isinstance(binding, dict):
        _add(blockers, "evaluation_input_not_registered")
        return None

    report_binding = (
        model_report.get("evaluation_input")
        if isinstance(model_report, dict)
        else None
    )
    if not isinstance(report_binding, dict):
        _add(blockers, "model_evaluation_report_input_binding_missing")
    elif report_binding != binding:
        _add(blockers, "model_evaluation_report_input_binding_mismatch")

    registered_digest = binding.get("sha256")
    if (
        not isinstance(registered_digest, str)
        or BARE_SHA256.fullmatch(registered_digest) is None
        or registered_digest == ZERO_SHA256
    ):
        _add(blockers, "evaluation_input_hash_invalid")
        registered_digest = None

    registered_task = binding.get("evaluation_task")
    if registered_task != evaluation_task:
        _add(blockers, "evaluation_input_task_mismatch")
    registered_split = binding.get("split")
    if registered_split != split:
        _add(blockers, "evaluation_input_split_mismatch")
    registered_scheme = binding.get("digest_scheme")
    if registered_scheme not in {
        RAW_INPUT_DIGEST_SCHEME,
        COMBINED_INPUT_DIGEST_SCHEME,
    }:
        _add(blockers, "evaluation_input_digest_scheme_invalid")
    elif supplied_digest_scheme != registered_scheme:
        _add(blockers, "evaluation_input_digest_scheme_mismatch")
    if not isinstance(binding.get("format"), str) or not binding["format"].strip():
        _add(blockers, "evaluation_input_format_missing")
    if not isinstance(binding.get("media_type"), str) or not binding[
        "media_type"
    ].strip():
        _add(blockers, "evaluation_input_media_type_missing")

    artifact_name = binding.get("artifact_path")
    held_out_path = bundle.get("held_out_predictions_path")
    if not isinstance(artifact_name, str) or not artifact_name:
        _add(blockers, "evaluation_input_artifact_missing")
    elif artifact_name != held_out_path:
        _add(blockers, "evaluation_input_artifact_path_mismatch")
    else:
        artifact_path = _resolve_artifact_path(artifact_name)
        if not artifact_path.is_file():
            _add(blockers, "evaluation_input_artifact_missing")
        else:
            try:
                stat = artifact_path.stat()
                artifact_digest = _artifact_digest(
                    str(artifact_path.resolve()), stat.st_size, stat.st_mtime_ns
                )
            except OSError:
                _add(blockers, "evaluation_input_artifact_unreadable")
            else:
                registered_bytes = binding.get("bytes")
                if (
                    isinstance(registered_bytes, bool)
                    or not isinstance(registered_bytes, int)
                    or registered_bytes <= 0
                ):
                    _add(blockers, "evaluation_input_bytes_invalid")
                elif registered_bytes != stat.st_size:
                    _add(blockers, "evaluation_input_artifact_size_mismatch")
                if registered_digest is not None and artifact_digest != registered_digest:
                    _add(blockers, "evaluation_input_artifact_hash_mismatch")
                elif registered_digest is not None:
                    resolution["evaluation_input_artifact_verified"] = True

    if registered_digest is not None:
        resolution["evaluation_input_sha256"] = registered_digest
        if supplied_digest is not None and supplied_digest != registered_digest:
            _add(blockers, "evaluation_input_hash_mismatch")
    resolution["evaluation_input_format"] = binding.get("format")
    resolution["evaluation_input_digest_scheme"] = registered_scheme
    return binding


def _task_matches_evaluator(evaluation_task: str, task_type: object) -> bool:
    normalized = str(task_type or "").upper()
    markers = _DATASET_TASK_MARKERS.get(evaluation_task, ())
    if evaluation_task == "lab_extraction":
        return all(marker in normalized for marker in markers)
    return any(marker in normalized for marker in markers)


def resolve_evaluation_context(
    evaluation_task: str,
    model_id: Optional[str],
    dataset_id: Optional[str],
    dataset_version: Optional[str],
    split: Optional[str],
    checkpoint: Optional[str],
    input_sha256: Optional[str],
    input_digest_scheme: Optional[str],
) -> dict[str, Any]:
    """Resolve an evaluation context against immutable local evidence.

    Resolution is fail-closed. Any absent, ambiguous, stale, or contradictory
    registry evidence leaves the run ``EXPLORATORY`` with explicit blockers.
    """
    normalized_model_id = _text(model_id)
    normalized_dataset_id = _text(dataset_id)
    normalized_dataset_version = _text(dataset_version)
    normalized_checkpoint = _text(checkpoint)
    normalized_input_sha256 = _text(input_sha256)
    normalized_input_digest_scheme = _text(input_digest_scheme)
    context: dict[str, Any] = {
        "model_id": normalized_model_id,
        # ``dataset`` is retained for persisted/API compatibility; its value is
        # now required to be the stable datasets[].id from tasks.json.
        "dataset": normalized_dataset_id,
        "dataset_version": normalized_dataset_version,
        "split": split,
        "checkpoint": normalized_checkpoint,
        "evaluation_input_sha256": normalized_input_sha256,
        "evaluation_input_digest_scheme": normalized_input_digest_scheme,
        "reporting_scope": REPORTING_SCOPE,
        "registry_resolution": {
            "model_id": None,
            "checkpoint_sha256": None,
            "checkpoint_artifact_verified": False,
            "evaluation_input_sha256": None,
            "evaluation_input_artifact_verified": False,
            "evaluation_input_format": None,
            "evaluation_input_digest_scheme": None,
            "dataset_id": None,
            "dataset_version": None,
            "task_id": None,
            "task_type": None,
            "split": None,
            "split_n": None,
            "exact_match": False,
        },
    }
    blockers: list[str] = []
    for field, value in (
        ("model_id", normalized_model_id),
        ("dataset", normalized_dataset_id),
        ("dataset_version", normalized_dataset_version),
        ("split", split),
        ("checkpoint", normalized_checkpoint),
        ("evaluation_input_sha256", normalized_input_sha256),
        ("evaluation_input_digest_scheme", normalized_input_digest_scheme),
    ):
        if not value:
            _add(blockers, field)
    if split and split not in REPORTABLE_SPLITS:
        _add(blockers, "held_out_test_split")

    supplied_digest: str | None = None
    if normalized_checkpoint:
        match = CHECKPOINT_SHA256.fullmatch(normalized_checkpoint)
        if match is None:
            _add(blockers, "checkpoint_sha256_format")
        else:
            supplied_digest = match.group(1)
            if supplied_digest == ZERO_SHA256:
                _add(blockers, "checkpoint_sha256_zero")
                supplied_digest = None

    supplied_input_digest: str | None = None
    if normalized_input_sha256:
        if BARE_SHA256.fullmatch(normalized_input_sha256) is None:
            _add(blockers, "evaluation_input_sha256_format")
        elif normalized_input_sha256 == ZERO_SHA256:
            _add(blockers, "evaluation_input_sha256_zero")
        else:
            supplied_input_digest = normalized_input_sha256

    models: list[dict[str, Any]] = []
    try:
        payload = _load_registry()
        raw_models = payload.get("models")
        if isinstance(raw_models, list):
            models = [item for item in raw_models if isinstance(item, dict)]
        else:
            _add(blockers, "model_registry_unavailable")
    except RegistryConfigurationError:
        _add(blockers, "model_registry_unavailable")

    model = next(
        (item for item in models if item.get("model_id") == normalized_model_id),
        None,
    )
    if normalized_model_id and model is None:
        _add(blockers, "model_not_registered")

    model_report: dict[str, Any] | None = None
    registered_digest: str | None = None
    evaluation_input: dict[str, Any] | None = None
    if model is not None:
        context["registry_resolution"]["model_id"] = model.get("model_id")
        bundle = model.get("artifact_bundle")
        if not isinstance(bundle, dict):
            bundle = {}
        candidate_digest = bundle.get("checkpoint_sha256")
        if (
            isinstance(candidate_digest, str)
            and BARE_SHA256.fullmatch(candidate_digest)
            and candidate_digest != ZERO_SHA256
        ):
            registered_digest = candidate_digest
        else:
            _add(blockers, "model_checkpoint_not_registered")

        if supplied_digest is not None and registered_digest is not None:
            if supplied_digest != registered_digest:
                owners = [
                    item.get("model_id")
                    for item in models
                    if (item.get("artifact_bundle") or {}).get("checkpoint_sha256")
                    == supplied_digest
                ]
                _add(
                    blockers,
                    "model_checkpoint_mismatch"
                    if owners
                    else "checkpoint_not_registered",
                )
            else:
                context["registry_resolution"]["checkpoint_sha256"] = (
                    f"sha256:{registered_digest}"
                )
                checkpoint_name = bundle.get("checkpoint_path")
                checkpoint_path = (
                    _resolve_artifact_path(checkpoint_name)
                    if isinstance(checkpoint_name, str) and checkpoint_name
                    else None
                )
                if checkpoint_path is None or not checkpoint_path.is_file():
                    _add(blockers, "checkpoint_artifact_missing")
                else:
                    try:
                        stat = checkpoint_path.stat()
                        actual_digest = _artifact_digest(
                            str(checkpoint_path.resolve()), stat.st_size, stat.st_mtime_ns
                        )
                    except OSError:
                        _add(blockers, "checkpoint_artifact_unreadable")
                    else:
                        if actual_digest != registered_digest:
                            _add(blockers, "checkpoint_artifact_hash_mismatch")
                        else:
                            context["registry_resolution"][
                                "checkpoint_artifact_verified"
                            ] = True

        model_report = _read_model_report(model, blockers)
        evaluation_input = _resolve_evaluation_input(
            model,
            model_report,
            evaluation_task,
            split,
            supplied_input_digest,
            normalized_input_digest_scheme,
            blockers,
            context["registry_resolution"],
        )
        if (
            normalized_dataset_version
            and bundle.get("dataset_version") != normalized_dataset_version
        ):
            _add(blockers, "model_dataset_version_mismatch")
        allowed_model_tasks = _MODEL_TASKS.get(evaluation_task, set())
        if model.get("task") not in allowed_model_tasks:
            _add(blockers, "evaluation_task_model_mismatch")
        if evaluation_task == "classification":
            supported_classes = model.get("supported_classes")
            if not isinstance(supported_classes, list) or len(supported_classes) != 2:
                _add(blockers, "evaluation_task_model_label_contract_mismatch")
    elif supplied_digest is not None:
        if not any(
            (item.get("artifact_bundle") or {}).get("checkpoint_sha256")
            == supplied_digest
            for item in models
        ):
            _add(blockers, "checkpoint_not_registered")

    try:
        task_audit = load_dataset_task_audit()
    except DatasetTaskAuditUnavailableError:
        task_audit = None
        _add(blockers, "dataset_task_evidence_unavailable")

    dataset: dict[str, Any] | None = None
    selected_task: dict[str, Any] | None = None
    if task_audit is not None and normalized_dataset_id:
        dataset_matches = [
            item
            for item in task_audit.get("datasets", [])
            if item.get("id") == normalized_dataset_id
        ]
        if not dataset_matches:
            _add(blockers, "dataset_not_registered")
        elif len(dataset_matches) > 1:
            _add(blockers, "dataset_id_ambiguous")
        elif normalized_dataset_version:
            dataset = dataset_matches[0]
            version_tasks = [
                task
                for task in dataset.get("tasks", [])
                if (task.get("preparation") or {}).get("dataset_version")
                == normalized_dataset_version
            ]
            if not version_tasks:
                _add(blockers, "dataset_version_not_registered")
            else:
                report_task_id = (
                    model_report.get("task_id")
                    if isinstance(model_report, dict)
                    else None
                )
                if isinstance(report_task_id, str):
                    exact_tasks = [
                        task
                        for task in version_tasks
                        if task.get("task_id") == report_task_id
                    ]
                    if not exact_tasks:
                        _add(blockers, "model_dataset_task_mismatch")
                    elif len(exact_tasks) > 1:
                        _add(blockers, "dataset_task_ambiguous")
                    else:
                        selected_task = exact_tasks[0]
                elif len(version_tasks) == 1:
                    selected_task = version_tasks[0]
                else:
                    _add(blockers, "dataset_task_ambiguous")

    if model_report is not None:
        if (
            normalized_dataset_id
            and model_report.get("dataset_id") != normalized_dataset_id
        ):
            _add(blockers, "model_dataset_mismatch")
        if (
            normalized_dataset_version
            and model_report.get("dataset_version") != normalized_dataset_version
        ):
            _add(blockers, "model_dataset_version_mismatch")

    if selected_task is not None and dataset is not None:
        preparation = selected_task.get("preparation") or {}
        context["registry_resolution"].update(
            {
                "dataset_id": dataset.get("id"),
                "dataset_version": preparation.get("dataset_version"),
                "task_id": selected_task.get("task_id"),
                "task_type": selected_task.get("type"),
            }
        )
        if selected_task.get("validation_ready") is not True:
            _add(blockers, "dataset_task_not_validation_ready")
        if selected_task.get("training_eligible") is not True:
            _add(blockers, "dataset_task_not_training_eligible")
        if selected_task.get("readiness") != "READY_FOR_TRAINING":
            _add(blockers, "dataset_task_readiness_unresolved")
        license_evidence = dataset.get("license")
        if (
            not isinstance(license_evidence, dict)
            or license_evidence.get("status") != "VERIFIED"
        ):
            _add(blockers, "dataset_license_not_verified")
        if not _task_matches_evaluator(evaluation_task, selected_task.get("type")):
            _add(blockers, "evaluation_task_dataset_mismatch")
        if split in REPORTABLE_SPLITS:
            split_count = (preparation.get("per_split") or {}).get(split)
            if (
                isinstance(split_count, bool)
                or not isinstance(split_count, int)
                or split_count <= 0
            ):
                _add(blockers, "dataset_split_not_registered")
            else:
                context["registry_resolution"].update(
                    {"split": split, "split_n": split_count}
                )
                if evaluation_input is not None:
                    registered_rows = evaluation_input.get("row_count")
                    if (
                        isinstance(registered_rows, bool)
                        or not isinstance(registered_rows, int)
                        or registered_rows <= 0
                    ):
                        _add(blockers, "evaluation_input_row_count_invalid")
                    elif registered_rows != split_count:
                        _add(blockers, "evaluation_input_row_count_mismatch")

    context["reporting_blockers"] = blockers
    context["reporting_status"] = (
        "ELIGIBLE_FOR_REPORTING" if not blockers else "EXPLORATORY"
    )
    context["registry_resolution"]["exact_match"] = not blockers
    revision = code_revision()
    context["code_revision"] = revision
    context["reproducibility_warnings"] = (
        ["CODE_COMMIT_NOT_RECORDED"]
        if revision["commit"] is None
        else ["UNCOMMITTED_CODE_CHANGES"]
        if revision["working_tree_clean"] is False
        else []
    )
    return context
