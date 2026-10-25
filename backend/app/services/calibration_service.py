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


def compute_brier_score(probabilities: np.ndarray, ground_truth: np.ndarray) -> float:
    """
    Computes Brier Score (BS = 1/N * sum (p_i - o_i)^2) (Eq. 15a).
    Lower is better (0.0 is perfect calibration and sharpness).
    """
    if len(probabilities) != len(ground_truth):
        raise ValueError("Length mismatch between probabilities and ground truth.")
    return float(np.mean((probabilities - ground_truth) ** 2))


def compute_expected_calibration_error(
    confidences: np.ndarray,
    correctness: np.ndarray,
    num_bins: int = 10
) -> Tuple[float, List[Dict[str, Any]]]:
    """
    Computes Expected Calibration Error (ECE) across B equal-width bins (Eq. 15b).
    ECE = sum_b (|S_b| / N) * |acc(S_b) - conf(S_b)|
    """
    bin_boundaries = np.linspace(0, 1, num_bins + 1)
    ece = 0.0
    n = len(confidences)
    bin_stats = []

    for i in range(num_bins):
        bin_lower = bin_boundaries[i]
        bin_upper = bin_boundaries[i + 1]

        # Samples in current bin S_b
        in_bin = (confidences > bin_lower) & (confidences <= bin_upper)
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
    Applies temperature scaling to calibrate modern neural network logits.
    p = softmax(z / T)
    """
    if temperature <= 0:
        raise ValueError("Temperature parameter T must be strictly positive.")
    scaled_logits = logits / temperature
    exp_scaled = np.exp(scaled_logits - np.max(scaled_logits, axis=-1, keepdims=True))
    probs = exp_scaled / np.sum(exp_scaled, axis=-1, keepdims=True)
    return probs
