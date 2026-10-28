"""Feature-space applicability gate for the 2-D research image models.

Each model gets a reference fitted on its own training images. Features are the spatially averaged
activations of every stage of the network (ResNet layers, EfficientNet stages, U-Net encoder
levels, the detector's ResNet stages), so both low-level statistics (colour, intensity, texture:
a greyscale CT slice is far from endoscopy colour) and high-level content are compared.

Per stage, features are standardised and modelled by a probabilistic-PCA Gaussian: k principal
directions with their own variances plus one isotropic variance for the rest, so the Mahalanobis
distance

    d^2 = sum_i (v_i . z)^2 / lambda_i  +  |residual(z)|^2 / sigma^2

is defined even with more dimensions than training images. Each stage's distance is divided by its
median over the calibration images, and an image's score combines its stage scores (their mean by
default: an image from another modality differs at most stages, while the mean stays close to 1 for
in-distribution images; a single extreme stage still raises it). The refusal threshold is a quantile
of the calibration images' scores, so about (1 - quantile) of in-distribution images are refused by
construction; held-out images and other image domains measure what the threshold actually does
(scripts/build_image_ood_references.py).

This checks resemblance to the training distribution. It is not an image-quality check and not a
guarantee: an image can resemble the training data and still be outside what the model handles.
"""

from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path
from typing import Any, Optional, Sequence

import numpy as np

SCORE_VERSION = "multistage-ppca-mahalanobis-v2"
COMBINATIONS = ("mean", "max")
DEFAULT_COMPONENTS = 64
DEFAULT_QUANTILE = 0.99
_STAGE_KEYS = ("center", "scale", "components", "eigenvalues")


class OodReferenceError(Exception):
    """The reference is missing, altered or does not belong to the checkpoint."""


def _fit_stage(fit: np.ndarray, components: int) -> dict[str, Any]:
    n, dims = fit.shape
    center = fit.mean(axis=0)
    scale = fit.std(axis=0)
    scale = np.where(scale > 1e-8 * max(float(scale.max()), 1e-12), scale, max(float(scale.max()), 1.0))
    z = (fit - center) / scale
    _, singular, vt = np.linalg.svd(z, full_matrices=False)
    eigenvalues = singular ** 2 / (n - 1)
    k = int(max(1, min(components, len(eigenvalues) - 1, dims - 1, max(n // 10, 1))))
    floor = 1e-6 * float(eigenvalues[0]) if eigenvalues[0] > 0 else 1e-12
    residual = eigenvalues[k:].sum() / max(dims - k, 1)
    return {"center": center, "scale": scale, "components": vt[:k], "eigenvalues": np.maximum(eigenvalues[:k], floor),
            "residual_variance": max(float(residual), floor), "normaliser": 1.0}


def _stage_distance(stage: dict[str, Any], features: np.ndarray) -> np.ndarray:
    z = (np.atleast_2d(np.asarray(features, dtype=np.float64)) - stage["center"]) / stage["scale"]
    projected = z @ stage["components"].T
    residual = z - projected @ stage["components"]
    return (projected ** 2 / stage["eigenvalues"]).sum(axis=1) + (residual ** 2).sum(axis=1) / stage["residual_variance"]


def stage_scores(reference: dict[str, Any], stages: Sequence[np.ndarray]) -> np.ndarray:
    """(images, stages) matrix of each stage's distance divided by its validation median."""
    if len(stages) != len(reference["stages"]):
        raise OodReferenceError("OOD_REFERENCE_FEATURES_MISMATCH")
    return np.column_stack([_stage_distance(stage, values) / stage["normaliser"] for stage, values in zip(reference["stages"], stages)])


def score(reference: dict[str, Any], stages: Sequence[np.ndarray]) -> np.ndarray:
    """One score per image: the mean (or maximum) of its normalised stage distances."""
    values = stage_scores(reference, stages)
    return values.max(axis=1) if reference.get("combine") == "max" else values.mean(axis=1)


def fit_reference(fit_stages: Sequence[np.ndarray], calibration_stages: Sequence[np.ndarray], *, components: int = DEFAULT_COMPONENTS,
                  quantile: float = DEFAULT_QUANTILE, combine: str = "mean", metadata: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    """Fit one Gaussian per stage on ``fit_stages`` and set normalisers and threshold from ``calibration_stages``."""
    fitted = []
    for values in fit_stages:
        values = np.asarray(values, dtype=np.float64)
        if values.ndim != 2 or values.shape[0] < 3:
            raise ValueError("At least three feature vectors per stage are needed to fit a reference.")
        fitted.append(_fit_stage(values, components))
    if combine not in COMBINATIONS:
        raise ValueError(f"combine must be one of {COMBINATIONS}")
    reference: dict[str, Any] = {"stages": fitted, "combine": combine}
    for stage, values in zip(fitted, calibration_stages):
        stage["normaliser"] = max(float(np.median(_stage_distance(stage, values))), 1e-12)
    calibration = score(reference, calibration_stages)
    reference["threshold"] = float(np.quantile(calibration, quantile))
    reference["metadata"] = {
        **(metadata or {}), "score_version": SCORE_VERSION, "stage_dimensions": [int(np.asarray(v).shape[1]) for v in fit_stages],
        "stage_components": [int(stage["components"].shape[0]) for stage in fitted],
        "fit_n": int(np.asarray(fit_stages[0]).shape[0]), "calibration_n": int(len(calibration)), "calibration_quantile": quantile,
        "stage_combination": combine,
    }
    return reference


def save_reference(path: Path, reference: dict[str, Any]) -> str:
    """Write the reference (no pickled objects) and return its SHA-256."""
    arrays: dict[str, np.ndarray] = {"threshold": np.float64(reference["threshold"]),
                                     "metadata": np.array(json.dumps(reference["metadata"], sort_keys=True))}
    for index, stage in enumerate(reference["stages"]):
        for key in _STAGE_KEYS:
            arrays[f"s{index}_{key}"] = stage[key]
        arrays[f"s{index}_residual_variance"] = np.float64(stage["residual_variance"])
        arrays[f"s{index}_normaliser"] = np.float64(stage["normaliser"])
    buffer = io.BytesIO()
    np.savez(buffer, **arrays)
    data = buffer.getvalue()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return hashlib.sha256(data).hexdigest()


def load_reference(path: Path, sha256: Optional[str], checkpoint_sha256: Optional[str]) -> dict[str, Any]:
    """Load a reference whose bytes match ``sha256`` and that was fitted on ``checkpoint_sha256``."""
    if not path.is_file():
        raise OodReferenceError("OOD_REFERENCE_MISSING")
    data = path.read_bytes()
    if hashlib.sha256(data).hexdigest() != sha256:
        raise OodReferenceError("OOD_REFERENCE_HASH_MISMATCH")
    with np.load(io.BytesIO(data), allow_pickle=False) as stored:
        metadata = json.loads(str(stored["metadata"]))
        if metadata.get("score_version") != SCORE_VERSION:
            raise OodReferenceError("OOD_REFERENCE_VERSION_UNSUPPORTED")
        stages = []
        for index in range(len(metadata["stage_dimensions"])):
            stage = {key: stored[f"s{index}_{key}"] for key in _STAGE_KEYS}
            stage["residual_variance"] = float(stored[f"s{index}_residual_variance"])
            stage["normaliser"] = float(stored[f"s{index}_normaliser"])
            stages.append(stage)
        reference = {"stages": stages, "threshold": float(stored["threshold"]), "metadata": metadata,
                     "combine": metadata.get("stage_combination", "mean")}
    if metadata.get("checkpoint_sha256") != checkpoint_sha256:
        raise OodReferenceError("OOD_REFERENCE_FOR_ANOTHER_CHECKPOINT")
    return reference
