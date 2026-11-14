"""Research inference for the tabular classifiers (ml_training.tabular) from typed values.

Each model is served only inside its registered input envelope (development-part ranges and categories,
docs/validation/models/<model_id>_input_envelope.json, SHA-256 checked against the registry). The checkpoint's SHA-256
is verified before it is loaded. Refusals are typed and name the field:

- MODEL_NOT_TABULAR, EXPLORATORY_ONLY (no Brier skill over the prevalence baseline on its held-out test),
- ENVELOPE_MISSING or ENVELOPE_CHANGED, CHECKPOINT_HASH_MISMATCH,
- UNKNOWN_FIELD, MISSING_REQUIRED_FIELD, TOO_MANY_BLANK_FIELDS, NOT_A_NUMBER, NOT_AN_ALLOWED_CODE, OUT_OF_DEVELOPMENT_RANGE,
  UNKNOWN_CATEGORY.

Output is a research probability (Platt-calibrated on the source cohort's validation part only), its validation-chosen
threshold and provenance; it is not a diagnosis and is not stored as patient evidence.
"""

from __future__ import annotations

import hashlib
import json
import math
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np

from app.services.model_inference import InferenceNotPermitted, evaluation_summary, get_model


def _pandas():
    """pandas (with scikit-learn and joblib) is needed only to run a tabular model; the app starts without it."""
    try:
        import pandas
    except ImportError as exc:
        raise InferenceNotPermitted("TABULAR_RUNTIME_UNAVAILABLE: pandas and scikit-learn are not installed on this server.") from exc
    return pandas
from app.services.model_registry import _resolve_artifact_path


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _model(model_id: str) -> dict:
    model = get_model(model_id)  # raises InferenceNotPermitted when the research gate is closed
    if model.get("task") != "tabular_classification":
        raise InferenceNotPermitted(f"MODEL_NOT_TABULAR: {model['display_name']} does not take typed table values.")
    return model


def _envelope(model: dict) -> dict:
    bundle = model["artifact_bundle"]
    if not bundle.get("input_envelope_path") or not bundle.get("input_envelope_sha256"):
        raise InferenceNotPermitted("ENVELOPE_MISSING: this model has no registered input envelope, so its inputs cannot be checked.")
    path = _resolve_artifact_path(bundle["input_envelope_path"])
    if not path.is_file() or _sha256(path) != bundle["input_envelope_sha256"]:
        raise InferenceNotPermitted("ENVELOPE_CHANGED: the input envelope file does not match its registered SHA-256.")
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=16)
def _checkpoint(path: str, sha256: str) -> dict:
    import joblib

    if _sha256(Path(path)) != sha256:
        raise InferenceNotPermitted("CHECKPOINT_HASH_MISMATCH: the checkpoint does not match its registered SHA-256; it was not loaded.")
    return joblib.load(path)


def _load(model: dict) -> dict:
    bundle = model["artifact_bundle"]
    return _checkpoint(str(_resolve_artifact_path(bundle["checkpoint_path"])), bundle["checkpoint_sha256"])


def _logit(p: np.ndarray) -> np.ndarray:
    p = np.clip(p, 1e-6, 1 - 1e-6)
    return np.log(p / (1 - p))


def score_frame(checkpoint: dict, frame) -> np.ndarray:
    """Calibrated probabilities for rows with the training feature columns (the same steps as training and evaluation)."""
    raw = checkpoint["pipeline"].predict_proba(frame[checkpoint["features"]])[:, 1]
    return checkpoint["platt"].predict_proba(_logit(raw).reshape(-1, 1))[:, 1]


def contract(model_id: str) -> dict:
    model = _model(model_id)
    envelope = _envelope(model)
    readiness = model.get("validation_readiness") or {}
    return {"model_id": model_id, "display_name": model["display_name"], "target": envelope["target"], "units": envelope["units"],
            "source": envelope["source"], "fields": envelope["fields"], "rules": envelope["rules"],
            "run_scope": readiness.get("run_scope"), "runnable": readiness.get("run_scope") == "RESEARCH",
            "threshold": (model["artifact_bundle"].get("decision_thresholds") or {}).get("positive"),
            "held_out_evaluation": evaluation_summary(model), "limitations": model.get("limitations", []),
            "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED"}


def predict(model_id: str, values: dict[str, Any]) -> dict:
    model = _model(model_id)
    readiness = model.get("validation_readiness") or {}
    if readiness.get("run_scope") != "RESEARCH":
        raise InferenceNotPermitted(f"EXPLORATORY_ONLY: {model['display_name']} showed no Brier skill over the prevalence baseline on its held-out "
                                    "test, so it is not run on new values.")
    envelope = _envelope(model)
    fields = {field["name"]: field for field in envelope["fields"]}
    unknown = sorted(set(values) - set(fields))
    if unknown:
        raise InferenceNotPermitted(f"UNKNOWN_FIELD: {', '.join(unknown)} are not inputs of this model.")
    row: dict[str, Any] = {}
    blank: list[str] = []
    for name, field in fields.items():
        value = values.get(name)
        if value is None or (isinstance(value, str) and not value.strip()):
            if not field.get("may_be_blank"):
                raise InferenceNotPermitted(f"MISSING_REQUIRED_FIELD: {name} was never blank in the development data, so it cannot be imputed.")
            blank.append(name)
            row[name] = np.nan
            continue
        if field["type"] == "number":
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise InferenceNotPermitted(f"NOT_A_NUMBER: {name} must be a number.") from exc
            if not math.isfinite(number):
                raise InferenceNotPermitted(f"NOT_A_NUMBER: {name} must be finite.")
            if field.get("allowed_values") is not None and number not in field["allowed_values"]:
                codes = ", ".join(f"{code:g}" for code in field["allowed_values"])
                raise InferenceNotPermitted(f"NOT_AN_ALLOWED_CODE: {name} = {number:g} is not one of the coded values {codes}.")
            if number < field["min"] or number > field["max"]:
                raise InferenceNotPermitted(f"OUT_OF_DEVELOPMENT_RANGE: {name} = {number:g} is outside {field['min']:g} to {field['max']:g} seen in "
                                            f"development ({envelope['units']}); check the unit.")
            row[name] = number
        else:
            text = str(value).strip()
            if text not in field["categories"]:
                raise InferenceNotPermitted(f"UNKNOWN_CATEGORY: {name} = {text!r} is not one of {', '.join(field['categories'][:12])}.")
            row[name] = text
    if len(blank) * 2 > len(fields):
        raise InferenceNotPermitted(f"TOO_MANY_BLANK_FIELDS: {len(blank)} of {len(fields)} fields are blank; at most half may be imputed.")
    checkpoint = _load(model)
    pd = _pandas()
    frame = pd.DataFrame([row], columns=checkpoint["features"])
    for name, field in fields.items():
        frame[name] = frame[name].astype(float) if field["type"] == "number" else frame[name].astype(object)
    probability = float(score_frame(checkpoint, frame)[0])
    threshold = float(checkpoint["threshold"])
    return {"model_id": model_id, "display_name": model["display_name"], "target": envelope["target"], "probability": probability,
            "threshold": threshold, "at_or_above_threshold": probability >= threshold, "imputed_fields": blank,
            "probability_semantics": "Platt-calibrated on the validation part of the source cohort only; not calibrated for any clinical population.",
            "threshold_rule": "Youden's J on the source cohort's validation part", "checkpoint_sha256": model["artifact_bundle"]["checkpoint_sha256"],
            "held_out_evaluation": evaluation_summary(model), "limitations": model.get("limitations", []),
            "output_status": "RESEARCH_ONLY_NOT_CLINICALLY_VALIDATED", "stored": False}
