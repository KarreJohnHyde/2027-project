"""Read-only comparisons of immutable registered research evaluation artifacts.

No weights, calibrators or thresholds are fitted here. Comparability requires
identical task, labels, dataset version and the actual labelled held-out units.
"""
from __future__ import annotations

import csv
import hashlib
import json
import math
import os
from functools import lru_cache
from pathlib import Path
import numpy as np
from app.services.evaluation_metrics import _auroc, _average_precision

from app.services import model_inference
from app.services.model_registry import _resolve_artifact_path
from app.config import PROJECT_ROOT

SCHEMA = "medtwin.arena.v1"
NOTICE = "Saved internal research evaluations; not new inference or clinical validation. Unpaired metric differences do not establish improvement."

MODEL_DATASETS = {
    "ptbxl_ecg_baseline": "ptb-xl-1.0.1", "ptbxl_ecg_demographic_fusion": "ptb-xl-1.0.1",
    "gi_kvasir_v2_classifier": "kvasir-v2", "gi_kvasir_seg_polyp_segmenter": "kvasir-seg",
    "gi_gastrovision_27class_classifier": "gastrovision", "angiography_stenosis_detector": "arcade",
    "angiography_syntax_segmenter": "arcade", "bone_fracture_detector": "bone-fracture-roboflow-v4",
    "brain_mri_stroke_lesion_segresnet": "isles-2022", "ct_kidney_tumour_segresnet": "kits19-labels",
}


def _evaluation_rights(model: dict) -> dict:
    """Fresh derivative computations obey the declared commercial purpose too.

    Historic report display is distinct from launching a new computation. No
    public URL, CC tag or existing prediction file silently grants use rights.
    """
    try:
        purpose = json.loads((Path(PROJECT_ROOT) / "dataset_registry/release_context.json").read_text())["training_purpose"]
    except (OSError, ValueError, KeyError, TypeError):
        return {"allowed": False, "reason": "DECLARED_PURPOSE_UNAVAILABLE"}
    terms = str((model.get("artifact_bundle") or {}).get("dataset_license") or "").upper()
    if purpose == "commercial_development" and any(term in terms for term in ("BY-NC", "NON-COMMERCIAL", "NONCOMMERCIAL", "RESEARCH ONLY", "RESEARCH-ONLY", "RESEARCH AND EDUCATIONAL")):
        return {"allowed": False, "reason": "SOURCE_TERMS_EXCLUDE_COMMERCIAL_USE", "purpose": purpose}
    dataset_id = MODEL_DATASETS.get(model["model_id"])
    if not dataset_id:
        return {"allowed": False, "reason": "EVIDENCE_BOUND_DATASET_RIGHTS_MAPPING_MISSING", "purpose": purpose}
    try:
        # Shared canonical evidence-bound rights gate; no purpose/registry edits.
        from ml_training.volumetric_manifest import enforce_training_license
        configured = os.getenv("MEDTWIN_COMPLETION_RIGHTS_REGISTRY", "").strip()
        registry = Path(configured) if configured else Path(PROJECT_ROOT) / "dataset_registry/tasks.json"
        evidence = enforce_training_license({"dataset_id": dataset_id}, registry)
        if purpose == "commercial_development":
            from app.services.model_usage_policy import usage_gate
            model_rights = usage_gate(model)
            if model_rights.get("profile") != "commercial" or not model_rights.get("allowed"):
                return {"allowed": False, "reason": "EVIDENCE_BOUND_COMMERCIAL_MODEL_REVIEW_REQUIRED", "purpose": purpose,
                        "dataset_id": dataset_id, "model_blockers": model_rights.get("blockers", [])}
        return {"allowed": True, "reason": "CANONICAL_EVIDENCE_BOUND_RIGHTS_GATE_PASSED", "purpose": purpose,
                "dataset_id": dataset_id, "registry_sha256": evidence.get("registry_sha256")}
    except (PermissionError, ImportError) as exc:
        return {"allowed": False, "reason": "CANONICAL_COMMERCIAL_RIGHTS_REVIEW_REQUIRED", "detail": str(exc), "purpose": purpose, "dataset_id": dataset_id}


def _digest(path: Path) -> str:
    return model_inference._checkpoint_hash(path)


def _binding(model: dict, report: dict) -> dict:
    bundle = model.get("artifact_bundle") or {}
    checkpoint = report.get("checkpoint") or {}
    checkpoint_sha = checkpoint.get("sha256") if isinstance(checkpoint, dict) else None
    fields = {"model_id": (report.get("model_id"), model["model_id"]),
              "dataset_version": (report.get("dataset_version"), bundle.get("dataset_version")),
              "checkpoint_sha256": (checkpoint_sha or report.get("checkpoint_sha256"), bundle.get("checkpoint_sha256"))}
    reasons = [f"REPORT_{key.upper()}_{'MISSING' if not actual or not expected else 'MISMATCH'}"
               for key, (actual, expected) in fields.items() if not actual or not expected or actual != expected]
    recorded = report.get("held_out_predictions")
    expected = bundle.get("held_out_predictions_path")
    if not isinstance(recorded, str) or not expected:
        reasons.append("REPORT_PREDICTION_PATH_BINDING_MISSING")
    elif _resolve_artifact_path(recorded).resolve() != _resolve_artifact_path(expected).resolve():
        reasons.append("REPORT_PREDICTION_PATH_BINDING_MISMATCH")
    return {"status": "VERIFIED_DECLARED_ARTIFACT_BINDING" if not reasons else "REPORT_BINDING_UNVERIFIED", "reasons": reasons,
            "scope": "Checks report declarations against registry identity and current paths; no historical prediction-byte hash or clinical validation is inferred."}


def _snapshot(model: dict) -> dict:
    bundle = model.get("artifact_bundle") or {}
    result = {"model_id": model["model_id"], "display_name": model.get("display_name", model["model_id"]),
              "task": model.get("task"), "labels": model.get("supported_classes", []),
              "dataset_version": bundle.get("dataset_version"),
              "checkpoint_sha256": bundle.get("checkpoint_sha256"),
              "preprocessing_version": bundle.get("preprocessing_version"),
              "calibration": bundle.get("calibration"), "decision_thresholds": bundle.get("decision_thresholds"),
              "gate": model_inference.research_gate(model), "clinical_activation": False,
              "evaluation_state": "UNAVAILABLE", "evaluation_sha256": None, "metrics": {},
              "test_n": None, "test_patients": None, "confidence_intervals_95": {},
              "report_binding": {"status": "REPORT_BINDING_UNVERIFIED", "reasons": ["REPORT_UNAVAILABLE"]}}
    try:
        path = _resolve_artifact_path(bundle["evaluation_report_path"])
        report = model_inference._report(model)
        result["report_binding"] = _binding(model, report)
        result.update(evaluation_state="SAVED_RESEARCH_EVALUATION", evaluation_sha256=_digest(path),
                      test_n=report.get("test_n", (report.get("test") or {}).get("n_images")),
                      test_patients=report.get("test_patients"),
                      confidence_intervals_95=report.get("confidence_intervals_95", {}))
        try:
            result["metrics"] = model_inference.evaluation_summary(model)
        except (KeyError, TypeError, ValueError):
            result["metrics_state"] = "TASK_SUMMARY_UNAVAILABLE_SEE_SOURCE_REPORT"
        result["evaluation_url"] = f"/research-models/{model['model_id']}/evaluation"
        result["available_diagnostics"] = [key for key in ("per_class", "per_label", "confusion_matrix", "reliability", "paired_difference", "arms") if key in report]
    except (OSError, ValueError, KeyError, TypeError):
        result["evaluation_reason"] = "REGISTERED_REPORT_MISSING_OR_UNREADABLE"
    return result


def list_models() -> dict:
    return {"schema_version": SCHEMA, "notice": NOTICE,
            "models": [_snapshot(m) for m in model_inference._load_registry()["models"] if m.get("research_inference")]}


@lru_cache(maxsize=32)
def _csv_units(path_string: str, size: int, mtime_ns: int, labels: tuple[str, ...]) -> tuple[str | None, int, str | None]:
    # Cache keyed by stat, never user supplied. Prediction masks/directories do
    # not prove matched cohorts and are intentionally unavailable to this path.
    path = Path(path_string)
    if path.suffix.lower() != ".csv" or size > 128 * 1024 * 1024:
        return None, 0, "MATCHED_LABELLED_UNITS_UNAVAILABLE"
    units: dict[str, list[str]] = {}
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        key = next((k for k in ("ecg_id", "sample_id", "image_id", "record_id") if k in fields), None)
        label_fields = [next((p + label for p in ("y_", "label_") if p + label in fields), None) for label in labels]
        if not key or "patient_id" not in fields or not labels or None in label_fields:
            return None, 0, "PATIENT_AND_LABELLED_UNIT_KEYS_UNAVAILABLE"
        for row in reader:
            if len(units) >= 1_000_000:
                return None, 0, "COHORT_LIMIT_EXCEEDED"
            identity = row.get(key, "")
            patient = row.get("patient_id", "")
            values = [row.get(field, "") for field in label_fields]
            if not identity or not patient or identity in units or any(v not in {"0", "1", "0.0", "1.0"} for v in values):
                return None, 0, "INVALID_OR_DUPLICATE_LABELLED_UNITS"
            units[identity] = [patient, *[str(int(float(v))) for v in values]]
    if not units:
        return None, 0, "EMPTY_HELD_OUT_COHORT"
    payload = json.dumps(sorted(units.items()), separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest(), len(units), None


def _cohort(model: dict) -> dict:
    value = (model.get("artifact_bundle") or {}).get("held_out_predictions_path")
    try:
        path = _resolve_artifact_path(value)
        stat = path.stat()
        digest, count, reason = _csv_units(str(path), stat.st_size, stat.st_mtime_ns, tuple(model.get("supported_classes", [])))
        return {"digest": digest, "n": count, "reason": reason, "prediction_sha256": _digest(path) if path.is_file() else None}
    except (OSError, TypeError, ValueError, csv.Error):
        return {"digest": None, "n": 0, "reason": "HELD_OUT_PREDICTIONS_UNAVAILABLE", "prediction_sha256": None}


def compare_models(left_id: str, right_id: str) -> dict:
    models = {m["model_id"]: m for m in model_inference._load_registry()["models"] if m.get("research_inference")}
    if left_id not in models or right_id not in models:
        raise KeyError("Unknown research model")
    left, right = models[left_id], models[right_id]
    a, b = _snapshot(left), _snapshot(right)
    reasons = []
    if left_id == right_id:
        reasons.append("SAME_MODEL_IS_NOT_INDEPENDENT_COMPARISON")
    if a["task"] != b["task"]:
        reasons.append("TASK_MISMATCH")
    if not a["labels"] or a["labels"] != b["labels"]:
        reasons.append("LABEL_DEFINITION_MISMATCH_OR_UNKNOWN")
    definitions = [(m.get("artifact_bundle") or {}).get("label_definition") for m in (left, right)]
    if not definitions[0] or definitions[0] != definitions[1]:
        reasons.append("TARGET_DEFINITION_MISMATCH_OR_UNKNOWN")
    if not a["dataset_version"] or a["dataset_version"] != b["dataset_version"]:
        reasons.append("DATASET_VERSION_MISMATCH_OR_UNKNOWN")
    rights = {"left": _evaluation_rights(left), "right": _evaluation_rights(right)}
    def eligible_cohort(model, gate):
        return _cohort(model) if gate["allowed"] else {"digest": None, "n": 0, "reason": gate["reason"], "prediction_sha256": None}
    ca, cb = eligible_cohort(left, rights["left"]), eligible_cohort(right, rights["right"])
    if not all(gate["allowed"] for gate in rights.values()):
        reasons.append("FRESH_COMPUTATION_RIGHTS_GATE_NOT_PASSED")
    if not ca["digest"] or not cb["digest"]:
        reasons.append("MATCHED_PATIENT_LABELLED_COHORT_UNVERIFIED")
    elif ca["digest"] != cb["digest"]:
        reasons.append("HELD_OUT_PATIENT_RECORD_OR_LABEL_MISMATCH")
    if a["evaluation_state"] != "SAVED_RESEARCH_EVALUATION" or b["evaluation_state"] != "SAVED_RESEARCH_EVALUATION":
        reasons.append("EVALUATION_UNAVAILABLE")
    if any(s["report_binding"]["status"] != "VERIFIED_DECLARED_ARTIFACT_BINDING" for s in (a, b)):
        reasons.append("REPORT_REGISTRY_BINDING_UNVERIFIED")
    for snapshot, cohort in ((a, ca), (b, cb)):
        if snapshot["test_n"] is None or snapshot["test_n"] != cohort["n"]:
            reasons.append("REPORT_COHORT_COUNT_MISMATCH_OR_UNKNOWN")
    deltas = {}
    if not reasons:
        for key in sorted(set(a["metrics"]) & set(b["metrics"])):
            av, bv = a["metrics"][key], b["metrics"][key]
            if key not in {"test_n", "test_patients"} and isinstance(av, (int, float)) and isinstance(bv, (int, float)):
                deltas[key] = bv - av
    paired = paired_comparison(left, right) if not reasons else {"status": "UNAVAILABLE", "reason": "COMPARABILITY_GATE_NOT_PASSED"}
    return {"schema_version": SCHEMA, "status": "COMPARABLE_RECORDED_COHORT" if not reasons else "COMPARISON_UNAVAILABLE",
            "reasons": list(dict.fromkeys(reasons)), "left": a, "right": b, "cohorts": {"left": ca, "right": cb},
            "computation_rights": rights,
            "right_minus_left": deltas, "paired_statistics": paired,
            "significance": paired.get("conclusion", "NOT_COMPUTED_NO_SUPERIORITY_CLAIM"),
            "notice": NOTICE, "clinical_activation": False}


MAX_PREDICTION_ROWS = 100_000
MAX_CURVE_POINTS = 201
BOOTSTRAP_ROUNDS = 500
BOOTSTRAP_SEED = 20261113


def _prediction_spec(model: dict, arm: str | None = None) -> tuple:
    path = _resolve_artifact_path(model["artifact_bundle"]["held_out_predictions_path"])
    stat = path.stat()
    if path.suffix.lower() != ".csv" or stat.st_size > 128 * 1024 * 1024:
        raise ValueError("BOUNDED_LABELLED_CSV_UNAVAILABLE")
    # The fusion CSV also contains an ECG-only arm: selecting the first p_ column
    # would silently evaluate the wrong model. This mapping is explicit.
    fusion = model.get("model_id") == "ptbxl_ecg_demographic_fusion"
    if arm and (not fusion or arm not in {"ecg_only", "fusion"}):
        raise ValueError("UNKNOWN_PREDICTION_ARM")
    prefix = f"{arm or 'fusion'}_p_" if fusion else "p_"
    return str(path), stat.st_size, stat.st_mtime_ns, tuple(model.get("supported_classes", [])), prefix


@lru_cache(maxsize=16)
def _prediction_matrix(path_string: str, size: int, mtime_ns: int, labels: tuple[str, ...], prefix: str) -> dict:
    if not labels:
        raise ValueError("LABEL_DEFINITION_UNAVAILABLE")
    path = Path(path_string)
    identities, patients, truths, scores = [], [], [], []
    with path.open(newline="", encoding="utf-8-sig") as handle:
        reader = csv.DictReader(handle)
        fields = reader.fieldnames or []
        key = next((name for name in ("ecg_id", "sample_id", "image_id", "record_id", "entry") if name in fields), None)
        patient_key = next((name for name in ("patient_id", "patient") if name in fields), None)
        truth_fields = [next((p + label for p in ("y_", "label_") if p + label in fields), None) for label in labels]
        multilabel = None not in truth_fields
        if not key or any(prefix + label not in fields for label in labels) or (not multilabel and "y_true" not in fields):
            raise ValueError("LABELLED_PROBABILITY_COLUMNS_UNAVAILABLE")
        seen = set()
        for row in reader:
            if len(identities) >= MAX_PREDICTION_ROWS:
                raise ValueError("PREDICTION_ROW_LIMIT_EXCEEDED")
            identity = row.get(key, "")
            if not identity or identity in seen:
                raise ValueError("INVALID_OR_DUPLICATE_PREDICTION_ID")
            seen.add(identity)
            if multilabel:
                raw_truth = [float(row[field]) for field in truth_fields]
                if any(item not in {0., 1.} for item in raw_truth):
                    raise ValueError("NON_BINARY_LABEL")
            else:
                if row["y_true"] not in labels:
                    raise ValueError("UNKNOWN_CLASS_LABEL")
                raw_truth = [float(row["y_true"] == label) for label in labels]
            probability = [float(row[prefix + label]) for label in labels]
            if any(not math.isfinite(p) or not 0 <= p <= 1 for p in probability):
                raise ValueError("INVALID_PROBABILITY")
            if not multilabel and abs(sum(probability) - 1.) > 1e-3:
                raise ValueError("MULTICLASS_PROBABILITIES_NOT_NORMALIZED")
            identities.append(identity)
            patients.append(row.get(patient_key, "") if patient_key else "")
            truths.append(raw_truth)
            scores.append(probability)
    if not identities:
        raise ValueError("EMPTY_PREDICTION_COHORT")
    order = np.argsort(identities)
    y, p = np.asarray(truths, dtype=int)[order], np.asarray(scores, dtype=float)[order]
    y.setflags(write=False); p.setflags(write=False)
    return {"ids": tuple(np.asarray(identities)[order]), "patients": tuple(np.asarray(patients)[order]),
            "y": y, "p": p, "multilabel": multilabel, "prediction_sha256": _digest(path), "probability_prefix": prefix}


def _curve(y: np.ndarray, p: np.ndarray) -> dict:
    positives, negatives = int(y.sum()), int(len(y) - y.sum())
    if positives == 0 or negatives == 0:
        return {"status": "UNAVAILABLE", "reason": "BOTH_LABEL_CLASSES_REQUIRED", "roc": [], "pr": []}
    order = np.argsort(-p, kind="stable")
    sy, sp = y[order], p[order]
    ends = np.r_[np.flatnonzero(np.diff(sp)), len(sp) - 1]
    tp = np.cumsum(sy)[ends]
    fp = ends + 1 - tp
    points = np.unique(np.linspace(0, len(ends) - 1, min(len(ends), MAX_CURVE_POINTS - 1), dtype=int))
    roc = [{"fpr": 0., "tpr": 0., "threshold": None}]
    pr = [{"recall": 0., "precision": 1., "threshold": None}]
    for i in points:
        roc.append({"fpr": float(fp[i] / negatives), "tpr": float(tp[i] / positives), "threshold": float(sp[ends[i]])})
        pr.append({"recall": float(tp[i] / positives), "precision": float(tp[i] / (tp[i] + fp[i])), "threshold": float(sp[ends[i]])})
    return {"status": "COMPUTED_FROM_SAVED_PREDICTIONS", "roc": roc, "pr": pr,
            "auroc": _auroc(y, p), "average_precision": _average_precision(y, p),
            "total_thresholds": len(ends), "display_downsampled": len(points) < len(ends), "positive_prevalence": positives / len(y)}


def _reliability(y: np.ndarray, p: np.ndarray) -> dict:
    bins = []
    assignment = np.minimum((p * 10).astype(int), 9)
    ece = 0.
    for index in range(10):
        mask = assignment == index
        count = int(mask.sum())
        observed = float(y[mask].mean()) if count else None
        mean = float(p[mask].mean()) if count else None
        if count:
            ece += count / len(y) * abs(observed - mean)
        bins.append({"lower": index / 10, "upper": (index + 1) / 10, "count": count,
                     "mean_probability": mean, "observed_frequency": observed})
    return {"bins": bins, "ece": ece, "brier": float(np.mean((p - y) ** 2)), "binning": "10 equal-width bins; p=1 included in final bin"}


def diagnostics(model_id: str, arm: str | None = None) -> dict:
    model = next((m for m in model_inference._load_registry()["models"] if m["model_id"] == model_id and m.get("research_inference")), None)
    if model is None:
        raise KeyError("Unknown research model")
    result = {"schema_version": "medtwin.arena-diagnostics.v1", "model_id": model_id, "arm": arm,
              "status": "UNAVAILABLE", "per_class": [], "confusion_matrix": None, "clinical_activation": False,
              "notice": "Computed from immutable saved predictions. Curves are not fabricated or independent validation; displayed points may be downsampled, metrics use all rows."}
    try:
        rights = _evaluation_rights(model)
        result["computation_rights"] = rights
        if not rights["allowed"]:
            return {**result, "reason": rights["reason"], "status": "RIGHTS_BLOCKED"}
        spec = _prediction_spec(model, arm)
        matrix = _prediction_matrix(*spec)
        labels, y, p = spec[3], matrix["y"], matrix["p"]
        thresholds = ((model.get("artifact_bundle") or {}).get("decision_thresholds") or {}).get("values") or {}
        if arm == "ecg_only":
            arm_report = (model_inference._report(model).get("arms") or {}).get("ecg_only") or {}
            thresholds = {entry["class"]: entry["threshold_from_validation"] for entry in arm_report.get("per_class", [])
                          if "class" in entry and "threshold_from_validation" in entry}
        entries = []
        for index, label in enumerate(labels):
            threshold = thresholds.get(label, .5)
            if not isinstance(threshold, (int, float)) or not 0 <= threshold <= 1:
                raise ValueError("INVALID_REGISTERED_THRESHOLD")
            predicted = p[:, index] >= threshold
            actual = y[:, index].astype(bool)
            confusion = {"tp": int((actual & predicted).sum()), "tn": int((~actual & ~predicted).sum()),
                         "fp": int((~actual & predicted).sum()), "fn": int((actual & ~predicted).sum()),
                         "threshold": threshold, "threshold_source": "REGISTERED_VALIDATION_POLICY" if label in thresholds else "PRESPECIFIED_0.5_DIAGNOSTIC_ONLY"}
            entries.append({"label": label, "n": len(y), "positives": int(y[:, index].sum()),
                            "curves": _curve(y[:, index], p[:, index]), "reliability": _reliability(y[:, index], p[:, index]), "binary_confusion": confusion})
        multiclass = None
        if not matrix["multilabel"]:
            counts = np.zeros((len(labels), len(labels)), dtype=int)
            np.add.at(counts, (y.argmax(axis=1), p.argmax(axis=1)), 1)
            multiclass = {"labels": labels, "counts": counts.tolist(), "rule": "ARGMAX_SAVED_PROBABILITIES", "rows": "actual", "columns": "predicted"}
        result.update(status="COMPUTED_FROM_SAVED_PREDICTIONS", n=len(y), patient_count=len(set(matrix["patients"])) if all(matrix["patients"]) else None,
                      prediction_sha256=matrix["prediction_sha256"], probability_prefix=matrix["probability_prefix"],
                      per_class=entries, confusion_matrix=multiclass, curve_point_limit=MAX_CURVE_POINTS,
                      report_binding=_snapshot(model)["report_binding"])
        if model_id == "ptbxl_ecg_demographic_fusion":
            result["paired_arms"] = _paired_cached(_prediction_spec(model, "ecg_only"), _prediction_spec(model, "fusion"))
    except (OSError, TypeError, ValueError, KeyError, csv.Error) as exc:
        result["reason"] = str(exc) if isinstance(exc, ValueError) else "SAVED_PREDICTIONS_UNAVAILABLE"
    return result


def _macro_auc(y, p):
    metrics = [_auroc(y[:, i], p[:, i]) for i in range(y.shape[1])]
    return float(np.mean(metrics)) if all(value is not None for value in metrics) else None


@lru_cache(maxsize=16)
def _paired_cached(left_spec: tuple, right_spec: tuple) -> dict:
    left, right = _prediction_matrix(*left_spec), _prediction_matrix(*right_spec)
    if left["ids"] != right["ids"] or left["patients"] != right["patients"] or not np.array_equal(left["y"], right["y"]):
        return {"status": "UNAVAILABLE", "reason": "PATIENT_RECORD_OR_LABEL_MISMATCH"}
    if not all(left["patients"]):
        return {"status": "UNAVAILABLE", "reason": "EXPLICIT_PATIENT_KEYS_REQUIRED"}
    patients = np.asarray(left["patients"])
    unique = np.unique(patients)
    if len(unique) < 20 or len(patients) > 20_000:
        return {"status": "UNAVAILABLE", "reason": "PATIENT_BOOTSTRAP_REQUIRES_20_TO_20000_PATIENT_RECORDS", "patient_count": len(unique)}
    y, a, b = left["y"], left["p"], right["p"]
    av, bv = _macro_auc(y, a), _macro_auc(y, b)
    if av is None or bv is None:
        return {"status": "UNAVAILABLE", "reason": "BOTH_CLASSES_REQUIRED_FOR_EVERY_LABEL"}
    groups = [np.flatnonzero(patients == patient) for patient in unique]
    rng, values = np.random.default_rng(BOOTSTRAP_SEED), []
    for _ in range(BOOTSTRAP_ROUNDS):
        index = np.concatenate([groups[i] for i in rng.integers(0, len(groups), len(groups))])
        ar, br = _macro_auc(y[index], a[index]), _macro_auc(y[index], b[index])
        if ar is not None and br is not None:
            values.append(br - ar)
    if len(values) < BOOTSTRAP_ROUNDS * .8:
        return {"status": "UNAVAILABLE", "reason": "TOO_MANY_DEGENERATE_BOOTSTRAP_DRAWS"}
    low, high = map(float, np.percentile(values, [2.5, 97.5]))
    return {"status": "COMPUTED_PAIRED_PATIENT_BOOTSTRAP", "metric": "MACRO_AUROC", "left": av, "right": bv,
            "right_minus_left": bv - av, "ci95": [low, high], "patient_count": len(unique), "record_count": len(y),
            "rounds": BOOTSTRAP_ROUNDS, "valid_rounds": len(values), "seed": BOOTSTRAP_SEED,
            "conclusion": "NO_DIFFERENCE_SHOWN" if low <= 0 <= high else "RIGHT_HIGHER_ON_RECORDED_INTERNAL_COHORT" if low > 0 else "LEFT_HIGHER_ON_RECORDED_INTERNAL_COHORT",
            "left_prediction_sha256": left["prediction_sha256"], "right_prediction_sha256": right["prediction_sha256"],
            "left_probability_prefix": left["probability_prefix"], "right_probability_prefix": right["probability_prefix"],
            "scope": "Paired patient-cluster percentile bootstrap on saved internal holdout predictions; not external or clinical superiority."}


def paired_comparison(left: dict, right: dict) -> dict:
    try:
        if not all(_evaluation_rights(model)["allowed"] for model in (left, right)):
            return {"status": "UNAVAILABLE", "reason": "FRESH_COMPUTATION_RIGHTS_GATE_NOT_PASSED"}
        return _paired_cached(_prediction_spec(left), _prediction_spec(right))
    except (OSError, TypeError, ValueError, KeyError, csv.Error):
        return {"status": "UNAVAILABLE", "reason": "VALID_LABELLED_PATIENT_PROBABILITIES_UNAVAILABLE"}
