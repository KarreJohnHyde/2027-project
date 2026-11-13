"""
Probability Calibration and Metric Evaluation Module for MedTwin.
Implements Section VI-F (Equation 15) of the IEEE manuscript.

Metrics implemented:
- Brier Score (BS) (Eq. 15a)
- Expected Calibration Error (ECE) (Eq. 15b)
- Temperature Scaling for probability calibration
"""

from typing import Dict, Any, List, Tuple
import numpy as np


def _finite_array(value: np.ndarray, name: str) -> np.ndarray:
    try:
        if np.iscomplexobj(value):
            raise ValueError(f"{name} must contain real values.")
        array = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a numeric array.") from exc
    if array.size == 0 or array.ndim == 0 or not np.all(np.isfinite(array)):
        raise ValueError(f"{name} must be a nonempty finite array.")
    return array


def compute_brier_score(
    probabilities: np.ndarray, ground_truth: np.ndarray, *, multiclass: bool = False
) -> float:
    """
    Mean squared probability error for binary or multilabel observations.

    The default preserves the existing elementwise mean (including class averaging
    for 2-D multilabel inputs). With ``multiclass=True``, require N x C normalized
    probabilities and one-hot truth and return the conventional mean of each row's
    SUM of class errors (range 0..2). Class indices must be encoded explicitly;
    broadcasting targets is refused. These definitions must not be mixed in reports.
    """
    probabilities = _finite_array(probabilities, "probabilities")
    ground_truth = _finite_array(ground_truth, "ground_truth")
    if probabilities.shape != ground_truth.shape or probabilities.ndim not in (1, 2):
        raise ValueError("probabilities and ground_truth must have identical 1-D or 2-D shapes.")
    if np.any((probabilities < 0) | (probabilities > 1)):
        raise ValueError("probabilities must be in [0, 1].")
    if not np.all((ground_truth == 0) | (ground_truth == 1)):
        raise ValueError("ground_truth must contain binary indicators.")
    squared_error = (probabilities - ground_truth) ** 2
    if multiclass:
        if probabilities.ndim != 2 or probabilities.shape[1] < 2:
            raise ValueError("Multiclass Brier requires N x C arrays with at least two classes.")
        if not np.allclose(probabilities.sum(axis=1), 1.0, atol=1e-7, rtol=0) or not np.all(ground_truth.sum(axis=1) == 1):
            raise ValueError("Multiclass probabilities must sum to one and truth must be one-hot.")
        return float(squared_error.sum(axis=1).mean())
    return float(squared_error.mean())


def compute_expected_calibration_error(
    confidences: np.ndarray,
    correctness: np.ndarray,
    num_bins: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Top-label/decision ECE for aligned 1-D confidence and binary correctness.

    Bins are [0, 1/B], (1/B, 2/B], ..., ((B-1)/B, 1]. Every observation,
    including confidence exactly zero or one, contributes exactly once. For a
    multiclass model, callers must explicitly choose top-label confidences and
    corresponding correctness (or evaluate each class separately); no flattening
    or implicit averaging of class probabilities is performed.
    """
    confidences = _finite_array(confidences, "confidences")
    correctness = _finite_array(correctness, "correctness")
    if confidences.ndim != 1 or confidences.shape != correctness.shape:
        raise ValueError("confidences and correctness must have identical 1-D shapes.")
    if np.any((confidences < 0) | (confidences > 1)):
        raise ValueError("confidences must be in [0, 1].")
    if not np.all((correctness == 0) | (correctness == 1)):
        raise ValueError("correctness must contain binary indicators.")
    if isinstance(num_bins, (bool, np.bool_)) or not isinstance(num_bins, (int, np.integer)) or num_bins < 1:
        raise ValueError("num_bins must be a positive integer.")
    bin_boundaries = np.linspace(0, 1, num_bins + 1)
    ece = 0.0
    bin_stats = []

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        # Samples in current bin S_b
        in_bin = ((confidences >= bin_lower) if i == 0 else (confidences > bin_lower)) & (confidences <= bin_upper)
        prop_in_bin = np.mean(in_bin)

        if prop_in_bin > 0:
            acc_in_bin = float(np.mean(correctness[in_bin]))
            conf_in_bin = float(np.mean(confidences[in_bin]))
            bin_error = abs(acc_in_bin - conf_in_bin)
            ece += bin_error * prop_in_bin

            bin_stats.append({
                "bin_index": i + 1,
                "range": [round(float(bin_lower), 2), round(float(bin_upper), 2)],
                "count": int(np.sum(in_bin)),
                "accuracy": round(acc_in_bin, 4),
                "confidence": round(conf_in_bin, 4),
                "calibration_gap": round(bin_error, 4)
            })

    return float(ece), bin_stats


def apply_temperature_scaling(logits: np.ndarray, temperature: float = 1.25) -> np.ndarray:
    """
    Apply multiclass softmax(z / T); this does not fit a calibrator.

    The historical default is retained for API compatibility, not as a learned
    calibration parameter. Use a temperature fitted on reserved development data.
    This function is not a sigmoid/multilabel calibrator.
    """
    logits = _finite_array(logits, "logits")
    if logits.ndim not in (1, 2) or logits.shape[-1] < 2:
        raise ValueError("logits must have a class axis of at least two classes (C or N x C).")
    if isinstance(temperature, (bool, np.bool_)) or not np.isscalar(temperature):
        raise ValueError("Temperature parameter T must be a finite positive scalar.")
    try:
        temperature = float(temperature)
    except (TypeError, ValueError) as exc:
        raise ValueError("Temperature parameter T must be a finite positive scalar.") from exc
    if not np.isfinite(temperature) or temperature <= 0:
        raise ValueError("Temperature parameter T must be a finite positive scalar.")
    # Center before dividing: tiny positive T cannot overflow the winning logit.
    # Finite extreme negative differences may reach -inf and correctly exponentiate to 0.
    with np.errstate(over="ignore", under="ignore"):
        scaled_logits = (logits - np.max(logits, axis=-1, keepdims=True)) / temperature
        exp_scaled = np.exp(scaled_logits)
    probs = exp_scaled / np.sum(exp_scaled, axis=-1, keepdims=True)
    return probs
