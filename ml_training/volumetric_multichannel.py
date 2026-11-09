"""Multi-channel 3-D MRI segmentation trainer and evaluator (brain MRI research models).

Preprocessing and inference are the serving module's own functions (app.services.volume_inference:
preprocess_multichannel, predict_multichannel, build_network), so the validation and held-out
evaluation below ran exactly the code that later serves uploads. Real data are refused unless
the dataset registry records ``license.authorization_status: VERIFIED`` (as in
ml_training.volumetric).

    python -m ml_training.volumetric_multichannel train --manifest <manifest.json> --model-id <id> \
        --channel-names DWI ADC --target-spacing 2 2 2 --patch-size 96 96 64 --device cuda --amp
    python -m ml_training.volumetric_multichannel envelope --run-dir <run> --output <envelope.json>
    python -m ml_training.volumetric_multichannel report --run-dir <run> --output <report.json>
    python -m ml_training.volumetric_multichannel smoke --work-dir <empty directory>

Training samples patches from a cache of the preprocessed volumes (float16 on disk, read by
memory map); the cache is derived data and lives outside Git.
"""

from __future__ import annotations

import argparse
import copy
import dataclasses
import hashlib
import json
import math
import sys
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np
import torch
import torch.nn.functional as F
from monai.losses import DiceCELoss, DiceLoss
from torch.utils.data import DataLoader, Dataset, Subset

from ml_training.common import ROOT, bootstrap_ci, environment, git_revision, load_resume, save_resume, set_seed, sha256_file
from ml_training.volumetric import _metric_for_class
from ml_training.volumetric_manifest import (
    DEFAULT_REGISTRY,
    build_manifest,
    enforce_training_license,
    validate_manifest,
    write_manifest,
)

sys.path.insert(0, str(ROOT / "backend"))
from app.services import volume_inference as serving  # noqa: E402  (the serving preprocessing and inference)

TRAINER_VERSION = serving.MULTICHANNEL_TRAINER
PREPROCESSING_VERSION = "nifti-foreground-crop-channel-zscore-resample-v2"
MAX_SAMPLING_COORDINATES = 10_000


@dataclass(frozen=True)
class Config:
    manifest_path: Path
    output_dir: Path
    model_id: str
    channel_names: tuple[str, ...]
    registry_path: Path = DEFAULT_REGISTRY
    device: str = "auto"
    epochs: int = 100
    iterations_per_epoch: int = 200
    batch_size: int = 2
    learning_rate: float = 3e-4
    weight_decay: float = 1e-5
    patch_size: tuple[int, int, int] = (96, 96, 64)
    init_filters: int = 16
    blocks_down: tuple[int, ...] = (1, 2, 2, 4)
    blocks_up: tuple[int, ...] = (1, 1, 1)
    dropout: float = 0.2
    foreground_probability: float = 0.6
    target_spacing: tuple[float, float, float] | None = None
    foreground_crop: bool = True
    overlap: float = 0.5
    sliding_window_mode: str = "gaussian"
    sw_batch_size: int = 2
    validate_every: int = 5
    seed: int = 20261105
    amp: bool = True
    workers: int = 2
    cache_dir: Path | None = None
    class_weights: tuple[float, ...] | None = None
    development_only: bool = False
    regions: dict[str, list[int]] = field(default_factory=dict)
    lesion_detection: bool = False
    volume_semantics: str = ""
    allow_synthetic_test_fixture: bool = False
    # "mr" (z-score over non-zero voxels, skull-stripped MRI) or "ct" (Hounsfield window from the training foreground).
    intensity: str = "mr"
    ct_clip_hu: tuple[float, float] | None = None
    ct_mean: float | None = None
    ct_std: float | None = None

    def spec(self) -> dict[str, Any]:
        if self.intensity == "ct":
            return {
                "version": PREPROCESSING_VERSION, "foreground_crop": False, "intensity": serving.CT_INTENSITY,
                "normalisation": "clip to the 0.5-99.5 percentiles of training foreground HU, then z-score with the training foreground mean and SD",
                "ct_clip_hu": [float(value) for value in self.ct_clip_hu or (0.0, 0.0)], "ct_mean": float(self.ct_mean or 0.0), "ct_std": float(self.ct_std or 1.0),
                "target_spacing_mm": None if self.target_spacing is None else [float(value) for value in self.target_spacing],
                "resampling": "trilinear (align_corners=False) for images and class probabilities; nearest-exact for training masks",
                "sliding_window_overlap": float(self.overlap), "sliding_window_mode": self.sliding_window_mode, "sw_batch_size": int(self.sw_batch_size),
            }
        return {
            "version": PREPROCESSING_VERSION,
            "foreground_crop": bool(self.foreground_crop),
            "normalisation": "per-channel z-score over that channel's non-zero voxels",
            "target_spacing_mm": None if self.target_spacing is None else [float(value) for value in self.target_spacing],
            "resampling": "trilinear (align_corners=False) for images and class probabilities; nearest-exact for training masks",
            "sliding_window_overlap": float(self.overlap),
            "sliding_window_mode": self.sliding_window_mode,
            "sw_batch_size": int(self.sw_batch_size),
        }

    def architecture(self, classes: int) -> dict[str, Any]:
        return {
            "name": "monai.networks.nets.SegResNet",
            "spatial_dims": 3,
            "in_channels": len(self.channel_names),
            "out_channels": int(classes),
            "init_filters": int(self.init_filters),
            "blocks_down": [int(value) for value in self.blocks_down],
            "blocks_up": [int(value) for value in self.blocks_up],
            "dropout_prob": float(self.dropout),
        }


def _device(requested: str) -> torch.device:
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    return torch.device("cuda" if requested == "cuda" or (requested == "auto" and torch.cuda.is_available()) else "cpu")


def header_spacing(image: nib.spatialimages.SpatialImage) -> tuple[float, float, float]:
    """Voxel spacing in millimetres exactly as the serving reader computes it."""
    unit_code = int(image.header["xyzt_units"]) & 0x07
    scale = serving.SPATIAL_UNIT_TO_MM.get(unit_code, 1.0)
    return tuple(float(value) * scale for value in image.header.get_zooms()[:3])


def load_case(case: dict[str, Any], root: Path) -> tuple[np.ndarray, np.ndarray, nib.spatialimages.SpatialImage]:
    image_nii = nib.load(str(root / case["image_path"]))
    data = np.asarray(image_nii.dataobj, dtype=np.float32)
    data = np.ascontiguousarray(np.moveaxis(data, 3, 0)) if data.ndim == 4 else data[None]
    mask = np.asarray(nib.load(str(root / case["mask_path"])).dataobj).round().astype(np.uint8)
    return data, mask, image_nii


def ct_statistics(cases: list[dict[str, Any]], root: Path, seed: int, per_case: int = 200_000) -> tuple[tuple[float, float], float, float]:
    """nnU-Net-style CT statistics from labelled (foreground) voxels of the training cases: the 0.5/99.5 percentile
    window, then the mean and SD of the clipped foreground."""
    rng = np.random.default_rng(seed)
    samples = []
    for case in cases:
        image, mask, _ = load_case(case, root)
        values = image[0][mask > 0]
        if len(values) > per_case:
            values = values[rng.choice(len(values), per_case, replace=False)]
        samples.append(values.astype(np.float32))
    pooled = np.concatenate(samples) if samples else np.zeros(1, np.float32)
    low, high = (float(value) for value in np.percentile(pooled, [0.5, 99.5]))
    clipped = np.clip(pooled, low, high)
    return (round(low, 2), round(high, 2)), round(float(clipped.mean()), 4), round(float(clipped.std()), 4)


def _spec_key(spec: dict[str, Any]) -> str:
    material = {key: spec.get(key) for key in ("version", "foreground_crop", "target_spacing_mm", "normalisation", "intensity", "ct_clip_hu", "ct_mean", "ct_std")}
    return hashlib.sha256(json.dumps(material, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def build_cache(cases: list[dict[str, Any]], root: Path, spec: dict[str, Any], cache_dir: Path, labels: list[int], seed: int) -> list[dict[str, Any]]:
    """Preprocess each training case once (serving preprocessing) into memory-mappable arrays."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    key = _spec_key(spec)
    entries = []
    for number, case in enumerate(cases):
        stem = cache_dir / f"{case['image_sha256'][:20]}-{case['mask_sha256'][:12]}-{key}"
        image_path, mask_path, coords_path = (Path(f"{stem}_{suffix}") for suffix in ("img.npy", "msk.npy", "fg.npz"))
        if not (image_path.is_file() and mask_path.is_file() and coords_path.is_file()):
            image, mask, image_nii = load_case(case, root)
            array, box, _cropped_shape = serving.preprocess_multichannel(image, header_spacing(image_nii), spec)
            cropped = mask[box]
            if tuple(array.shape[1:]) != tuple(cropped.shape):
                resized = F.interpolate(torch.from_numpy(cropped[None, None].astype(np.float32)), size=tuple(array.shape[1:]), mode="nearest-exact")
                cropped = resized[0, 0].numpy().round().astype(np.uint8)
            rng = np.random.default_rng([seed, number])
            coords = {}
            for label in labels:
                found = np.argwhere(cropped == label).astype(np.int32)
                if len(found) > MAX_SAMPLING_COORDINATES:
                    found = found[rng.choice(len(found), MAX_SAMPLING_COORDINATES, replace=False)]
                coords[str(label)] = found
            np.save(image_path, array.astype(np.float16))
            np.save(mask_path, np.ascontiguousarray(cropped, dtype=np.uint8))
            np.savez(coords_path, **coords)
        entries.append({"case_id": case["case_id"], "image": str(image_path), "mask": str(mask_path), "coords": str(coords_path)})
    return entries


class PatchStream(Dataset):
    """Deterministic patch for every global sample index: epoch e, iteration i, item b."""

    def __init__(self, entries: list[dict[str, Any]], patch: tuple[int, int, int], foreground_probability: float, total: int, seed: int) -> None:
        self.entries = entries
        self.patch = tuple(int(value) for value in patch)
        self.foreground_probability = float(foreground_probability)
        self.total = int(total)
        self.seed = int(seed)
        self.coords = []
        for entry in entries:
            with np.load(entry["coords"]) as stored:
                self.coords.append({int(label): stored[label] for label in stored.files if len(stored[label])})

    def __len__(self) -> int:
        return self.total

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        rng = np.random.default_rng([self.seed, int(index)])
        which = int(rng.integers(len(self.entries)))
        entry, coords = self.entries[which], self.coords[which]
        image = np.load(entry["image"], mmap_mode="r")
        mask = np.load(entry["mask"], mmap_mode="r")
        shape = mask.shape
        center = None
        if coords and rng.random() < self.foreground_probability:
            labels = sorted(coords)
            points = coords[labels[int(rng.integers(len(labels)))]]
            center = points[int(rng.integers(len(points)))]
        slices = []
        for axis, (length, size) in enumerate(zip(shape, self.patch)):
            room = max(0, int(length) - size)
            start = int(np.clip(int(center[axis]) - size // 2, 0, room)) if center is not None else int(rng.integers(room + 1))
            slices.append(slice(start, start + size))
        image_patch = np.asarray(image[(slice(None), *slices)], dtype=np.float32)
        mask_patch = np.asarray(mask[tuple(slices)], dtype=np.int64)
        padding = [(max(0, size - have) // 2, max(0, size - have) - max(0, size - have) // 2) for size, have in zip(self.patch, mask_patch.shape)]
        if any(before or after for before, after in padding):
            # The sliding-window inferer pads with zeros, so training pads the same way.
            image_patch = np.pad(image_patch, [(0, 0), *padding], mode="constant")
            mask_patch = np.pad(mask_patch, padding, mode="constant")
        for axis in range(3):
            if rng.random() < 0.5:
                image_patch = np.flip(image_patch, axis=axis + 1)
                mask_patch = np.flip(mask_patch, axis=axis)
        scale = rng.uniform(0.9, 1.1, size=(image_patch.shape[0], 1, 1, 1)).astype(np.float32)
        shift = rng.uniform(-0.1, 0.1, size=(image_patch.shape[0], 1, 1, 1)).astype(np.float32)
        image_patch = image_patch * scale + shift
        return torch.from_numpy(np.ascontiguousarray(image_patch)), torch.from_numpy(np.ascontiguousarray(mask_patch)[None])


def _payload(config: Config, manifest: dict[str, Any], model: torch.nn.Module, *, epoch: int, best_epoch: int, best_score: float) -> dict[str, Any]:
    return {
        "kind": "volumetric_semantic_segmenter",
        "trainer_version": TRAINER_VERSION,
        "model_id": config.model_id,
        "epoch": int(epoch),
        "best_epoch": int(best_epoch),
        "best_validation_mean_case_dice": float(best_score),
        "state_dict": {key: value.detach().cpu() for key, value in model.state_dict().items()},
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": sha256_file(config.manifest_path),
        "labels": manifest["labels"],
        "channels": list(config.channel_names),
        "architecture": config.architecture(len(manifest["labels"])),
        "preprocessing": config.spec(),
        "preprocessing_version": PREPROCESSING_VERSION,
        "patch_size": [int(value) for value in config.patch_size],
        "seed": int(config.seed),
        "volume_semantics": config.volume_semantics,
    }


def _components(binary: np.ndarray) -> tuple[np.ndarray, int]:
    from scipy import ndimage

    return ndimage.label(binary, structure=np.ones((3, 3, 3), dtype=bool))


def case_metrics(prediction: np.ndarray, reference: np.ndarray, labels: list[dict[str, Any]], regions: dict[str, list[int]],
                 spacing: tuple[float, float, float], lesion_detection: bool) -> dict[str, Any]:
    voxel_ml = float(np.prod(spacing)) / 1000.0
    classes = {str(label["id"]): _metric_for_class(prediction, reference, int(label["id"])) for label in labels[1:]}
    region_metrics = {}
    for name, members in regions.items():
        predicted, expected = np.isin(prediction, members), np.isin(reference, members)
        region_metrics[name] = _metric_for_class(predicted.astype(np.uint8), expected.astype(np.uint8), 1)
    for item in [*classes.values(), *region_metrics.values()]:
        item["predicted_ml"] = round(item["predicted_voxels"] * voxel_ml, 4)
        item["reference_ml"] = round(item["reference_voxels"] * voxel_ml, 4)
    defined = [item["dice"] for item in classes.values() if item["dice"] is not None]
    result = {"classes": classes, "regions": region_metrics, "macro_foreground_dice": float(np.mean(defined)) if defined else None,
              "voxel_spacing_mm": [round(value, 6) for value in spacing]}
    if lesion_detection:
        reference_components, reference_count = _components(reference > 0)
        predicted_components, predicted_count = _components(prediction > 0)
        detected = len(set(np.unique(reference_components[(prediction > 0) & (reference_components > 0)]).tolist()) - {0})
        matched_predictions = len(set(np.unique(predicted_components[(reference > 0) & (predicted_components > 0)]).tolist()) - {0})
        result["lesions"] = {"reference": int(reference_count), "detected": int(detected), "predicted": int(predicted_count),
                             "false_positive_components": int(predicted_count - matched_predictions)}
    return result


@torch.no_grad()
def evaluate(network: torch.nn.Module, payload: dict[str, Any], cases: list[dict[str, Any]], root: Path, dev: torch.device,
             regions: dict[str, list[int]], lesion_detection: bool, prediction_dir: Path | None = None) -> list[dict[str, Any]]:
    network.eval()
    results = []
    if prediction_dir is not None:
        prediction_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        image, reference, image_nii = load_case(case, root)
        spacing = header_spacing(image_nii)
        prediction = serving.predict_multichannel(network, payload, dev, image, spacing)
        metrics = case_metrics(prediction, reference, payload["labels"], regions, spacing, lesion_detection)
        results.append({"case_id": case["case_id"], "patient_id": case["patient_id"], **metrics})
        if prediction_dir is not None:
            saved = nib.Nifti1Image(prediction, image_nii.affine)
            saved.header.set_zooms(image_nii.header.get_zooms()[:3])
            saved.header.set_xyzt_units(*image_nii.header.get_xyzt_units())
            nib.save(saved, str(prediction_dir / f"{case['case_id']}.nii.gz"))
    return results


def _mean(values: list[float]) -> float | None:
    return float(np.mean(values)) if values else None


def _ci(values: list[float], seed: int, patients: list[str]) -> dict[str, Any]:
    """Percentile bootstrap of the mean, resampling patients (all of a patient's scans together)."""
    array = np.asarray(values, dtype=float)
    if len(array) < 5:
        return {"status": "NOT_COMPUTED_TOO_FEW_CASES"}
    return bootstrap_ci(lambda index: float(array[index].mean()), len(array), np.asarray(patients), rounds=2000, seed=seed, unit="patient")


def _agreement(pairs: list[tuple[float, float]]) -> dict[str, Any]:
    if len(pairs) < 3:
        return {"n_patients": len(pairs), "status": "NOT_COMPUTED_TOO_FEW_CASES"}
    difference = np.asarray([predicted - reference for predicted, reference in pairs])
    bias, sd = float(difference.mean()), float(difference.std(ddof=1))
    return {"n_patients": len(pairs), "bias": round(bias, 3), "limits_of_agreement": [round(bias - 1.96 * sd, 3), round(bias + 1.96 * sd, 3)],
            "mean_absolute_error": round(float(np.abs(difference).mean()), 3),
            "reference_mean": round(float(np.mean([reference for _, reference in pairs])), 3)}


def summarise(results: list[dict[str, Any]], labels: list[dict[str, Any]], regions: dict[str, list[int]], seed: int) -> dict[str, Any]:
    per_structure, region_summary, indices = {}, {}, {}
    for label in labels[1:]:
        key = str(label["id"])
        scored = [case for case in results if case["classes"][key]["dice"] is not None]
        dice = [case["classes"][key]["dice"] for case in scored]
        iou = [case["classes"][key]["iou"] for case in results if case["classes"][key]["iou"] is not None]
        per_structure[label["name"]] = {"mean_dice": _mean(dice), "mean_dice_95ci": _ci(dice, seed, [case["patient_id"] for case in scored]), "mean_iou": _mean(iou),
                                        "scored_cases": len(dice),
                                        "reference_positive_cases": sum(case["classes"][key]["reference_voxels"] > 0 for case in results),
                                        "both_empty_cases_excluded": len(results) - len(dice)}
        indices[f"{label['name']}_volume_ml"] = _agreement([(case["classes"][key]["predicted_ml"], case["classes"][key]["reference_ml"]) for case in results])
    for name in regions:
        scored = [case for case in results if case["regions"][name]["dice"] is not None]
        dice = [case["regions"][name]["dice"] for case in scored]
        region_summary[name] = {"mean_dice": _mean(dice), "mean_dice_95ci": _ci(dice, seed, [case["patient_id"] for case in scored]),
                                "scored_cases": len(dice), "labels": regions[name]}
        indices[f"{name}_volume_ml"] = _agreement([(case["regions"][name]["predicted_ml"], case["regions"][name]["reference_ml"]) for case in results])
    scored = [case for case in results if case["macro_foreground_dice"] is not None]
    macro = [case["macro_foreground_dice"] for case in scored]
    metrics: dict[str, Any] = {"mean_case_macro_dice": _mean(macro), "mean_case_macro_dice_95ci": _ci(macro, seed, [case["patient_id"] for case in scored]),
                               "per_structure": per_structure}
    if region_summary:
        metrics["regions"] = region_summary
    if results and "lesions" in results[0]:
        reference = sum(case["lesions"]["reference"] for case in results)
        detected = sum(case["lesions"]["detected"] for case in results)
        predicted = sum(case["lesions"]["predicted"] for case in results)
        false_positive = sum(case["lesions"]["false_positive_components"] for case in results)
        sensitivity = detected / reference if reference else None
        precision = (predicted - false_positive) / predicted if predicted else (0.0 if reference else None)
        if sensitivity is None or precision is None:
            f1 = None
        else:
            f1 = 0.0 if sensitivity + precision == 0 else 2 * sensitivity * precision / (sensitivity + precision)
        metrics["lesion_detection"] = {
            "definition": "26-connected components; a reference lesion is detected when any predicted voxel overlaps it; a predicted component overlapping no reference voxel is a false positive",
            "reference_lesions": reference, "detected_lesions": detected, "predicted_components": predicted,
            "false_positive_components": false_positive, "lesion_sensitivity": sensitivity, "component_precision": precision, "lesion_f1": f1,
            "false_positive_components_per_case": false_positive / len(results)}
        if len(per_structure) == 1:
            name, key = labels[1]["name"], str(labels[1]["id"])
            volumes = sorted(case["classes"][key]["reference_ml"] for case in results if case["classes"][key]["reference_voxels"] > 0)
            if len(volumes) >= 9:
                cuts = np.percentile(volumes, [100 / 3, 200 / 3])
                bands = {}
                for band, (low, high) in {"smallest_third": (-1, cuts[0]), "middle_third": (cuts[0], cuts[1]), "largest_third": (cuts[1], math.inf)}.items():
                    dice = [case["classes"][key]["dice"] for case in results
                            if case["classes"][key]["reference_voxels"] > 0 and low < case["classes"][key]["reference_ml"] <= high]
                    bands[band] = {"reference_ml_range": [None if low < 0 else round(float(low), 2), None if high == math.inf else round(float(high), 2)],
                                   "cases": len(dice), "mean_dice": _mean(dice)}
                metrics["dice_by_reference_volume"] = {"structure": name, "bands": bands}
    return {"metrics": metrics, "clinical_indices": indices}


def training_loss(config: Config, classes: int, dev):
    if config.class_weights is None:
        return DiceCELoss(to_onehot_y=True, softmax=True, batch=True)
    weights = np.asarray(config.class_weights, dtype=float)
    if len(weights) != classes or not np.isfinite(weights).all() or (weights <= 0).any():
        raise ValueError("Class weights must be finite, positive and match every label including background")
    dice = DiceLoss(include_background=False, to_onehot_y=True, softmax=True, batch=True)
    ce = torch.nn.CrossEntropyLoss(weight=torch.tensor(weights, dtype=torch.float32, device=dev))
    def loss(logits, masks):
        return dice(logits, masks) + ce(logits, masks[:, 0].long())
    return loss


def run_training(config: Config) -> dict[str, Any]:
    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    license_gate = enforce_training_license(manifest, config.registry_path, allow_synthetic_test_fixture=config.allow_synthetic_test_fixture)
    validation = validate_manifest(manifest, verify_hashes=True)
    channels = {int(case.get("channels", 1)) for case in manifest["cases"]}
    if channels != {len(config.channel_names)}:
        raise ValueError(f"Manifest images have {sorted(channels)} channel(s); --channel-names lists {len(config.channel_names)}.")
    divisor = 2 ** (len(config.blocks_down) - 1)
    if any(size % divisor for size in config.patch_size):
        raise ValueError(f"Every patch dimension must be a multiple of {divisor}.")

    dev = _device(config.device)
    amp = bool(config.amp and dev.type == "cuda")
    set_seed(config.seed)
    if dev.type == "cuda":
        # Deterministic cuDNN 3-D convolutions are several times slower, and CUDA training is not bit-exact anyway.
        torch.backends.cudnn.deterministic = False
        torch.backends.cudnn.benchmark = True
    root = Path(manifest["dataset_root"])
    labels = manifest["labels"]
    splits = {split: [case for case in manifest["cases"] if case["split"] == split] for split in ("train", "val", "test")}
    config.output_dir.mkdir(parents=True, exist_ok=True)
    cache_dir = config.cache_dir or (config.output_dir / "cache")
    if config.intensity == "ct" and config.ct_clip_hu is None:
        # Statistics from the training split only; validation and test cases never shape the preprocessing.
        window, mean, std = ct_statistics(splits["train"], root, config.seed)
        config = dataclasses.replace(config, ct_clip_hu=window, ct_mean=mean, ct_std=std)

    started = time.monotonic()
    entries = build_cache(splits["train"], root, config.spec(), cache_dir, [int(label["id"]) for label in labels[1:]], config.seed)
    cache_seconds = round(time.monotonic() - started, 1)

    network = serving.build_network({"trainer_version": TRAINER_VERSION, "architecture": config.architecture(len(labels))}).to(dev)
    optimizer = torch.optim.AdamW(network.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=config.epochs, eta_min=config.learning_rate * 0.01)
    loss_function = training_loss(config, len(labels), dev)
    scaler = torch.amp.GradScaler("cuda", enabled=amp)
    # Training state is written after every epoch to output_dir/resume.pt; a rerun with the same settings continues from it.
    resume_path = config.output_dir / "resume.pt"
    # Bound to the manifest's content (splits and cases), not only its path: a regenerated manifest starts fresh.
    identity = {key: (str(value) if isinstance(value, Path) else value) for key, value in asdict(config).items()
                if key not in ("workers", "device", "cache_dir", "registry_path")} | {
        "manifest_sha256": sha256_file(config.manifest_path), "dataset_version": manifest["dataset_version"]}
    resumed = load_resume(resume_path, identity)
    start_epoch = 1 if resumed is None else int(resumed["epoch"]) + 1
    per_epoch = config.iterations_per_epoch * config.batch_size
    # A resumed run samples the remaining epochs' patches from a new seed (recorded in execution.json).
    stream = PatchStream(entries, config.patch_size, config.foreground_probability, per_epoch * (config.epochs - start_epoch + 1),
                         config.seed + start_epoch - 1)
    loader = DataLoader(stream, batch_size=config.batch_size, shuffle=False, num_workers=config.workers,
                        persistent_workers=config.workers > 0, prefetch_factor=4 if config.workers > 0 else None)

    execution: dict[str, Any] = {
        "execution_status": "RUNNING", "trainer_version": TRAINER_VERSION, "model_id": config.model_id,
        "manifest_path": str(config.manifest_path.resolve()), "manifest_sha256": sha256_file(config.manifest_path),
        "dataset_id": manifest["dataset_id"], "dataset_version": manifest["dataset_version"],
        "synthetic_test_fixture": manifest["synthetic_test_fixture"], "license_gate": license_gate, "manifest_validation": validation,
        "split_counts": {split: len(cases) for split, cases in splits.items()},
        "environment": environment(), "git": git_revision(),
        "config": {**{key: (str(value) if isinstance(value, Path) else value) for key, value in asdict(config).items()},
                   "device_effective": dev.type, "amp_effective": amp, "preprocessing": config.spec(),
                   "architecture": config.architecture(len(labels))},
        "determinism": "seeded sampling and initialisation; cuDNN autotuning on CUDA (benchmark on, deterministic off), so a rerun can differ slightly",
        "cache": {"directory": str(cache_dir.resolve()), "seconds": cache_seconds, "cases": len(entries)},
        "epochs": [], "model_registry_mutation": "NONE",
    }
    execution_path = config.output_dir / "execution.json"
    execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")

    best_epoch, best_score = 0, -1.0
    best_state = copy.deepcopy({key: value.detach().cpu() for key, value in network.state_dict().items()})
    if resumed is not None:
        network.load_state_dict(resumed["model"])
        optimizer.load_state_dict(resumed["optimizer"])
        scheduler.load_state_dict(resumed["scheduler"])
        scaler.load_state_dict(resumed["scaler"])
        best_epoch, best_score, best_state = int(resumed["best_epoch"]), float(resumed["best_score"]), resumed["best_state"]
        execution["epochs"] = list(resumed["epoch_records"])
        execution["resumed_from_epoch"] = int(resumed["epoch"])
        print(json.dumps({"resumed_from_epoch": int(resumed["epoch"]), "best_epoch_so_far": best_epoch}), flush=True)
    batches = iter(loader)
    for epoch in range(start_epoch, config.epochs + 1):
        network.train()
        losses, tick = [], time.monotonic()
        for _ in range(config.iterations_per_epoch):
            images, masks = next(batches)
            images, masks = images.to(dev, non_blocking=True), masks.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=amp):
                logits = network(images)
            loss = loss_function(logits.float(), masks)
            scaler.scale(loss).backward()
            scaler.unscale_(optimizer)
            torch.nn.utils.clip_grad_norm_(network.parameters(), 12.0)
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))
        scheduler.step()
        record: dict[str, Any] = {"epoch": epoch, "mean_train_loss": float(np.mean(losses)), "train_seconds": round(time.monotonic() - tick, 1),
                                  "learning_rate": float(optimizer.param_groups[0]["lr"])}
        if epoch % config.validate_every == 0 or epoch == config.epochs:
            payload = _payload(config, manifest, network, epoch=epoch, best_epoch=best_epoch, best_score=best_score)
            tick = time.monotonic()
            results = evaluate(network, payload, splits["val"], root, dev, config.regions, False)
            macro = [case["macro_foreground_dice"] for case in results if case["macro_foreground_dice"] is not None]
            score = float(np.mean(macro)) if macro else -1.0
            record.update({"validation_mean_case_macro_dice": score, "validation_seconds": round(time.monotonic() - tick, 1)})
            record["validation_per_structure_dice"] = {
                label["name"]: _mean([case["classes"][str(label["id"])]["dice"] for case in results
                                      if case["classes"][str(label["id"])]["dice"] is not None]) for label in labels[1:]}
            if score > best_score:
                best_epoch, best_score = epoch, score
                best_state = copy.deepcopy({key: value.detach().cpu() for key, value in network.state_dict().items()})
                torch.save({**_payload(config, manifest, network, epoch=epoch, best_epoch=best_epoch, best_score=best_score)}, config.output_dir / "best.pt")
            torch.save({**_payload(config, manifest, network, epoch=epoch, best_epoch=best_epoch, best_score=best_score),
                        "optimizer_state_dict": optimizer.state_dict()}, config.output_dir / "last.pt")
        execution["epochs"].append(record)
        print(json.dumps(record), flush=True)
        execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
        save_resume(resume_path, identity, {"epoch": epoch, "model": network.state_dict(), "optimizer": optimizer.state_dict(),
                                            "scheduler": scheduler.state_dict(), "scaler": scaler.state_dict(), "best_epoch": best_epoch,
                                            "best_score": best_score, "best_state": best_state, "epoch_records": execution["epochs"]})

    network.load_state_dict(best_state)
    best_payload = _payload(config, manifest, network, epoch=best_epoch, best_epoch=best_epoch, best_score=best_score)
    if config.development_only:
        execution.update({"execution_status": "DEVELOPMENT_COMPLETE_TEST_NOT_EVALUATED",
                          "selection": {"criterion": "validation mean case macro foreground Dice", "best_epoch": best_epoch, "best_score": best_score},
                          "checkpoint": {"path": str((config.output_dir / "best.pt").resolve()), "sha256": sha256_file(config.output_dir / "best.pt")},
                          "held_out_test": {"status": "NOT_EVALUATED", "case_count": 0, "reason": "Development experiment; the exposed old test is not reused for model selection"},
                          "registry_claim": "No registry publication or upload authorization; independent final evaluation required"})
        execution_path.write_text(json.dumps(execution, indent=2) + "\n")
        return execution
    tick = time.monotonic()
    prediction_dir = config.output_dir / "held_out_predictions"
    test_results = evaluate(network, best_payload, splits["test"], root, dev, config.regions, config.lesion_detection, prediction_dir)
    summary = summarise(test_results, labels, config.regions, config.seed)
    execution.update({
        "execution_status": "COMPLETE",
        "selection": {"criterion": "validation mean of case-level macro foreground Dice (serving inference path)", "best_epoch": best_epoch, "best_score": best_score},
        "held_out_test": {"case_count": len(test_results), "patients": len({case["patient_id"] for case in test_results}),
                          "seconds": round(time.monotonic() - tick, 1), **summary, "cases": test_results},
        "checkpoint": {"path": str((config.output_dir / "best.pt").resolve()), "sha256": sha256_file(config.output_dir / "best.pt")},
        "held_out_predictions": str(prediction_dir.resolve()),
        "registry_claim": "No registry-ready or validated status is emitted by this trainer.",
    })
    execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    return execution


def build_envelope(run_dir: Path, output: Path, nonzero_margin: float = 0.05) -> dict[str, Any]:
    """Development (train + validation) geometry and occupancy, then the gate applied to the held-out test cases."""
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    manifest = json.loads(Path(execution["manifest_path"]).read_text(encoding="utf-8"))
    root = Path(manifest["dataset_root"])
    channels = execution["config"]["channel_names"]
    development = [case for case in manifest["cases"] if case["split"] in ("train", "val")]
    ct = execution["config"].get("intensity") == "ct"
    spacings, shapes, occupancy, orientations, percentiles = [], [], [], set(), []
    for case in development:
        image = nib.load(str(root / case["image_path"]))
        orientations.add("".join(nib.aff2axcodes(image.affine)))
        spacings.append(header_spacing(image))
        shapes.append(tuple(int(value) for value in image.shape[:3]))
        data = np.asarray(image.dataobj)
        data = np.moveaxis(data, 3, 0) if data.ndim == 4 else data[None]
        if ct:
            percentiles.append(serving.ct_percentiles(data[0].astype(np.float32)))
        else:
            occupancy.append(float(np.any(data != 0, axis=0).mean()))
    spacings_array, shapes_array = np.asarray(spacings), np.asarray(shapes)
    in_plane = np.concatenate([spacings_array[:, 0], spacings_array[:, 1]])
    envelope = {
        "model_id": execution["model_id"], "dataset_id": manifest["dataset_id"], "dataset_version": manifest["dataset_version"],
        "manifest_sha256": execution["manifest_sha256"],
        "derived_from": "NIfTI headers and voxels of the development cases (manifest train and validation splits); test cases do not shape the range",
        "development_cases": len(development), "ndim": [4] if len(channels) > 1 else [3, 4], "channels": channels,
        "in_plane_spacing_mm": {"min": float(in_plane.min()), "max": float(in_plane.max())},
        "in_plane_square_pixels": bool(np.allclose(spacings_array[:, 0], spacings_array[:, 1], rtol=serving.SQUARE_PIXEL_TOLERANCE)),
        "slice_spacing_mm": {"min": float(spacings_array[:, 2].min()), "max": float(spacings_array[:, 2].max())},
        "slice_axis_last": False,
        "matrix": {axis: {"min": int(shapes_array[:, index].min()), "max": int(shapes_array[:, index].max())} for index, axis in enumerate(("i", "j", "k"))},
        "orientations": sorted(orientations),
    }
    if ct:
        lows, highs = [low for low, _ in percentiles], [high for _, high in percentiles]
        envelope["hu_percentiles"] = {"p01": {"min": round(min(lows), 1), "max": round(max(lows), 1)},
                                      "p99": {"min": round(min(highs), 1), "max": round(max(highs), 1)}, "margin_hu": 100.0,
                                      "note": "1st and 99th intensity percentiles of each development CT volume (every 4th voxel per axis)."}
    else:
        envelope["nonzero_fraction"] = {"min": round(float(min(occupancy)), 4), "max": round(float(max(occupancy)), 4), "margin": nonzero_margin,
                                        "development_cases_above_half": int(sum(value > 0.5 for value in occupancy)),
                                        "note": "Cases with more than half their voxels non-zero are probably not skull-stripped; when there are any, "
                                                "the range cannot tell a head with skull from a skull-stripped brain."}
    accepted, refusals, warnings = 0, {}, {}
    test_cases = [case for case in manifest["cases"] if case["split"] == "test"]
    for case in test_cases:
        try:
            volume = serving.read_volume(root / case["image_path"], envelope)
        except serving.VolumeInputError as exc:
            for code in exc.codes:
                refusals[code] = refusals.get(code, 0) + 1
            continue
        accepted += 1
        for warning in volume.warnings:
            code = warning.split(" ")[0]
            warnings[code] = warnings.get(code, 0) + 1
    envelope["held_out_test_cases"] = {"total": len(test_cases), "accepted_by_gate": accepted, "refusal_reasons": refusals, "warnings": warnings}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(envelope, indent=2) + "\n", encoding="utf-8")
    return envelope


def build_report(run_dir: Path, output: Path, extra: dict[str, Any]) -> dict[str, Any]:
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    test = execution["held_out_test"]
    # The summary is recomputed from the stored per-case results with the current summarise(), so a run
    # trained before a fix to the summary statistics is reported with the fixed statistics.
    manifest = json.loads(Path(execution["manifest_path"]).read_text(encoding="utf-8"))
    test = {**test, **summarise(test["cases"], manifest["labels"], execution["config"].get("regions") or {}, int(execution["config"]["seed"]))}
    report = {
        "model_id": execution["model_id"], "run_id": run_dir.name, "task_type": "volumetric_semantic_segmentation",
        "dataset_id": execution["dataset_id"], "dataset_version": execution["dataset_version"],
        "split_counts": execution["split_counts"], "split_method": "patients split by sha256(seed:patient_id) ordering (ml_training.volumetric_manifest)",
        "test_n": test["case_count"], "test_patients": test["patients"],
        "metrics": test["metrics"], "clinical_indices": test["clinical_indices"],
        "selection": execution["selection"], "epochs_run": len(execution["epochs"]),
        "config": execution["config"], "determinism": execution["determinism"],
        "checkpoint": execution["checkpoint"], "held_out_predictions": execution["held_out_predictions"],
        "evaluation_path": "app.services.volume_inference.predict_multichannel (the serving function), float16 autocast on CUDA",
        "cases": test["cases"], **extra,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return report


def create_synthetic_fixture(work_dir: Path, seed: int = 20261105) -> Path:
    """Small two-channel NIfTI pairs for an isolated execution test (generated, not patient data)."""
    if work_dir.exists() and any(work_dir.iterdir()):
        raise ValueError("Synthetic smoke work directory must be empty.")
    data_root = work_dir / "fixture"
    data_root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    grid = np.indices((20, 20, 12))
    pairs = []
    for index in range(8):
        patient = f"synthetic_patient_{index:02d}"
        mask = (((grid[0] - (6 + index)) ** 2 + (grid[1] - 9) ** 2 + (grid[2] - 6) ** 2) <= 9).astype(np.uint8)
        brain = (((grid[0] - 10) ** 2 / 81 + (grid[1] - 10) ** 2 / 81 + (grid[2] - 6) ** 2 / 30) <= 1)
        first = np.where(brain, 1.0 + rng.normal(0, 0.05, mask.shape) + mask * 1.5, 0).astype(np.float32)
        second = np.where(brain, 2.0 + rng.normal(0, 0.05, mask.shape) - mask * 1.0, 0).astype(np.float32)
        mask = (mask & brain).astype(np.uint8)
        affine = np.diag([2.0, 2.0, 3.0, 1.0])
        nib.save(nib.Nifti1Image(np.stack([first, second], axis=-1), affine), str(data_root / f"{patient}_image.nii.gz"))
        nib.save(nib.Nifti1Image(mask, affine), str(data_root / f"{patient}_mask.nii.gz"))
        pairs.append({"patient_id": patient, "case_id": patient, "image_path": f"{patient}_image.nii.gz", "mask_path": f"{patient}_mask.nii.gz"})
    manifest = build_manifest(dataset_id="synthetic-multichannel-fixture", dataset_root=data_root, pairs=pairs,
                              labels={0: "background", 1: "fixture_lesion"}, seed=seed, val_fraction=0.25, test_fraction=0.25,
                              discovery={"layout": "GENERATED_SYNTHETIC_TEST_FIXTURE", "generator": TRAINER_VERSION}, synthetic_test_fixture=True)
    return write_manifest(manifest, work_dir / "manifest.json")


def _config(args: argparse.Namespace, *, synthetic: bool = False) -> Config:
    return Config(
        manifest_path=args.manifest, output_dir=args.output_dir, model_id=args.model_id, channel_names=tuple(args.channel_names),
        registry_path=args.registry, device=args.device, epochs=args.epochs, iterations_per_epoch=args.iterations_per_epoch,
        batch_size=args.batch_size, learning_rate=args.learning_rate, weight_decay=args.weight_decay, patch_size=tuple(args.patch_size),
        init_filters=args.init_filters, blocks_down=tuple(args.blocks_down), blocks_up=tuple(args.blocks_up), dropout=args.dropout,
        foreground_probability=args.foreground_probability, target_spacing=None if args.target_spacing is None else tuple(args.target_spacing),
        foreground_crop=args.foreground_crop, overlap=args.overlap, sliding_window_mode=args.sliding_window_mode, sw_batch_size=args.sw_batch_size,
        validate_every=args.validate_every, seed=args.seed, amp=args.amp, workers=args.workers, cache_dir=args.cache_dir,
        regions=json.loads(args.regions) if args.regions else {}, lesion_detection=args.lesion_detection,
        volume_semantics=args.volume_semantics, allow_synthetic_test_fixture=synthetic, intensity=getattr(args, "intensity", "mr"),
        class_weights=None if args.class_weights is None else tuple(args.class_weights), development_only=args.development_only)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    train = sub.add_parser("train")
    train.add_argument("--manifest", type=Path, required=True)
    train.add_argument("--output-dir", type=Path, required=True)
    train.add_argument("--model-id", required=True)
    train.add_argument("--channel-names", nargs="+", required=True)
    train.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    train.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    train.add_argument("--epochs", type=int, default=100)
    train.add_argument("--iterations-per-epoch", type=int, default=200)
    train.add_argument("--batch-size", type=int, default=2)
    train.add_argument("--learning-rate", type=float, default=3e-4)
    train.add_argument("--weight-decay", type=float, default=1e-5)
    train.add_argument("--patch-size", type=int, nargs=3, default=(96, 96, 64))
    train.add_argument("--init-filters", type=int, default=16)
    train.add_argument("--blocks-down", type=int, nargs="+", default=(1, 2, 2, 4))
    train.add_argument("--blocks-up", type=int, nargs="+", default=(1, 1, 1))
    train.add_argument("--dropout", type=float, default=0.2)
    train.add_argument("--foreground-probability", type=float, default=0.6)
    train.add_argument("--target-spacing", type=float, nargs=3)
    train.add_argument("--foreground-crop", action=argparse.BooleanOptionalAction, default=True)
    train.add_argument("--overlap", type=float, default=0.5)
    train.add_argument("--sliding-window-mode", choices=("gaussian", "constant"), default="gaussian")
    train.add_argument("--sw-batch-size", type=int, default=2)
    train.add_argument("--validate-every", type=int, default=5)
    train.add_argument("--seed", type=int, default=20261105)
    train.add_argument("--amp", action=argparse.BooleanOptionalAction, default=True)
    train.add_argument("--workers", type=int, default=2)
    train.add_argument("--cache-dir", type=Path)
    train.add_argument("--class-weights", nargs="+", type=float)
    train.add_argument("--development-only", action="store_true", help="Select on validation only; do not evaluate test labels or publish a model")
    train.add_argument("--regions", help='JSON, e.g. {"whole_tumour": [1, 2, 3]}')
    train.add_argument("--lesion-detection", action=argparse.BooleanOptionalAction, default=False)
    train.add_argument("--intensity", choices=("mr", "ct"), default="mr",
                       help="mr: z-score over non-zero voxels (skull-stripped MRI); ct: Hounsfield window from the training foreground")
    train.add_argument("--volume-semantics", default="Predicted voxel count x header voxel volume for this upload. Research output, not a clinical measurement.")
    envelope = sub.add_parser("envelope")
    envelope.add_argument("--run-dir", type=Path, required=True)
    envelope.add_argument("--output", type=Path, required=True)
    report = sub.add_parser("report")
    report.add_argument("--run-dir", type=Path, required=True)
    report.add_argument("--output", type=Path, required=True)
    report.add_argument("--extra", help="JSON object merged into the report (licence, limitations)")
    smoke = sub.add_parser("smoke")
    smoke.add_argument("--work-dir", type=Path, required=True)
    args = parser.parse_args(argv)

    if args.command == "envelope":
        print(json.dumps(build_envelope(args.run_dir, args.output)["held_out_test_cases"]))
        return 0
    if args.command == "report":
        report = build_report(args.run_dir, args.output, json.loads(args.extra) if args.extra else {})
        print(json.dumps({"test_n": report["test_n"], "mean_case_macro_dice": report["metrics"]["mean_case_macro_dice"]}))
        return 0
    if args.command == "smoke":
        manifest = create_synthetic_fixture(args.work_dir)
        config = Config(manifest_path=manifest, output_dir=args.work_dir / "run", model_id="synthetic_smoke", channel_names=("A", "B"),
                        device="cpu", epochs=2, iterations_per_epoch=2, batch_size=2, patch_size=(16, 16, 8), init_filters=8,
                        blocks_down=(1, 1), blocks_up=(1,), validate_every=1, amp=False, workers=0, target_spacing=(2.0, 2.0, 2.0),
                        lesion_detection=True, regions={"any_lesion": [1]}, sw_batch_size=1, allow_synthetic_test_fixture=True)
        result = run_training(config)
        print(json.dumps({"execution_status": result["execution_status"], "best_epoch": result["selection"]["best_epoch"],
                          "held_out_cases": result["held_out_test"]["case_count"]}))
        return 0
    result = run_training(_config(args))
    if result["execution_status"] == "DEVELOPMENT_COMPLETE_TEST_NOT_EVALUATED":
        print(json.dumps({"execution_status": result["execution_status"], "best_epoch": result["selection"]["best_epoch"],
                          "checkpoint_sha256": result["checkpoint"]["sha256"]}))
        return 0
    print(json.dumps({"execution_status": result["execution_status"], "best_epoch": result["selection"]["best_epoch"],
                      "held_out_cases": result["held_out_test"]["case_count"], "checkpoint_sha256": result["checkpoint"]["sha256"],
                      "mean_case_macro_dice": result["held_out_test"]["metrics"]["mean_case_macro_dice"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
