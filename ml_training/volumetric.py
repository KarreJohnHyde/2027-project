"""Deterministic patch-based 3-D NIfTI segmentation trainer and evaluator.

This module is a research execution path, not a clinical inference adapter.  It
never mutates the model registry.  A real-data run is refused before any volume
is loaded unless the live dataset registry explicitly records
``license.authorization_status: VERIFIED``.

An isolated end-to-end CPU smoke run is available for CI::

    python -m ml_training.volumetric smoke --work-dir <empty-directory>

Real-data invocation (only after the registry authorization gate is resolved)::

    python -m ml_training.volumetric train --manifest manifest.json \
      --output-dir artifacts/training/run --device cuda --amp
"""

from __future__ import annotations

import argparse
import copy
import json
import math
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Sequence

import nibabel as nib
import numpy as np
import torch
from monai.inferers import sliding_window_inference
from monai.losses import DiceCELoss
from monai.networks.nets import UNet
from torch.utils.data import DataLoader, Dataset

from ml_training.common import ROOT, environment, git_revision, seed_worker, set_seed, sha256_file
from ml_training.volumetric_manifest import (
    DEFAULT_REGISTRY,
    ManifestValidationError,
    build_manifest,
    enforce_training_license,
    validate_manifest,
    write_manifest,
)


TRAINER_VERSION = "volumetric-monai-unet-v1"
PREPROCESSING_VERSION = "nifti-native-grid-nonzero-zscore-v1"


@dataclass(frozen=True)
class TrainConfig:
    manifest_path: Path
    output_dir: Path
    registry_path: Path = DEFAULT_REGISTRY
    device: str = "auto"
    epochs: int = 20
    batch_size: int = 2
    learning_rate: float = 1e-3
    weight_decay: float = 1e-5
    patch_size: tuple[int, int, int] = (96, 96, 32)
    channels: tuple[int, ...] = (16, 32, 64, 128)
    patches_per_case: int = 2
    workers: int = 0
    seed: int = 20261024
    amp: bool = False
    resume: Path | None = None
    save_predictions: bool = False
    torch_threads: int | None = None
    allow_synthetic_test_fixture: bool = False


def _resolve_device(requested: str) -> torch.device:
    if requested not in {"auto", "cpu", "cuda"}:
        raise ValueError("device must be one of auto, cpu or cuda")
    if requested == "cuda" and not torch.cuda.is_available():
        raise RuntimeError("CUDA was requested but is not available.")
    return torch.device("cuda" if requested == "cuda" or (requested == "auto" and torch.cuda.is_available()) else "cpu")


def _load_case(case: dict[str, Any], root: Path) -> tuple[np.ndarray, np.ndarray, nib.spatialimages.SpatialImage]:
    image_nii = nib.load(str(root / case["image_path"]))
    mask_nii = nib.load(str(root / case["mask_path"]))
    image = np.asarray(image_nii.dataobj, dtype=np.float32)
    mask = np.asarray(mask_nii.dataobj).round().astype(np.int64)
    return image, mask, image_nii


def _normalise(image: np.ndarray) -> np.ndarray:
    finite = np.isfinite(image)
    nonzero = finite & (image != 0)
    sample = image[nonzero] if int(nonzero.sum()) >= 8 else image[finite]
    mean = float(sample.mean()) if sample.size else 0.0
    std = float(sample.std()) if sample.size else 1.0
    if not math.isfinite(std) or std < 1e-6:
        std = 1.0
    output = (image - mean) / std
    output[~finite] = 0
    return output.astype(np.float32, copy=False)


def _pad_to_patch(image: np.ndarray, mask: np.ndarray, patch: Sequence[int]) -> tuple[np.ndarray, np.ndarray]:
    padding = []
    for length, target in zip(image.shape, patch):
        total = max(0, int(target) - int(length))
        padding.append((total // 2, total - total // 2))
    if any(before or after for before, after in padding):
        image = np.pad(image, padding, mode="constant")
        mask = np.pad(mask, padding, mode="constant")
    return image, mask


def _sample_patch(
    image: np.ndarray,
    mask: np.ndarray,
    patch_size: Sequence[int],
    rng: np.random.Generator,
) -> tuple[np.ndarray, np.ndarray]:
    image, mask = _pad_to_patch(image, mask, patch_size)
    foreground = np.argwhere(mask > 0)
    use_foreground = len(foreground) > 0 and rng.random() < 0.75
    starts = []
    center = foreground[int(rng.integers(len(foreground)))] if use_foreground else None
    for axis, (length, patch) in enumerate(zip(image.shape, patch_size)):
        maximum = length - int(patch)
        if maximum <= 0:
            starts.append(0)
        elif center is None:
            starts.append(int(rng.integers(maximum + 1)))
        else:
            starts.append(int(np.clip(int(center[axis]) - int(patch) // 2, 0, maximum)))
    slices = tuple(slice(start, start + int(size)) for start, size in zip(starts, patch_size))
    image_patch = image[slices]
    mask_patch = mask[slices]
    for axis in range(3):
        if rng.random() < 0.5:
            image_patch = np.flip(image_patch, axis=axis)
            mask_patch = np.flip(mask_patch, axis=axis)
    return np.ascontiguousarray(image_patch), np.ascontiguousarray(mask_patch)


class PatchDataset(Dataset):
    """One or more deterministic foreground-biased patches per patient case."""

    def __init__(
        self,
        cases: list[dict[str, Any]],
        root: Path,
        patch_size: Sequence[int],
        patches_per_case: int,
        seed: int,
    ) -> None:
        self.cases = cases
        self.root = root
        self.patch_size = tuple(int(item) for item in patch_size)
        self.patches_per_case = int(patches_per_case)
        self.seed = int(seed)
        self.epoch = 0

    def set_epoch(self, epoch: int) -> None:
        self.epoch = int(epoch)

    def __len__(self) -> int:
        return len(self.cases) * self.patches_per_case

    def __getitem__(self, index: int) -> tuple[torch.Tensor, torch.Tensor]:
        case_index = index // self.patches_per_case
        image, mask, _ = _load_case(self.cases[case_index], self.root)
        rng = np.random.default_rng(self.seed + self.epoch * 1_000_003 + index)
        image, mask = _sample_patch(_normalise(image), mask, self.patch_size, rng)
        return torch.from_numpy(image[None]), torch.from_numpy(mask[None])


def _build_model(classes: int, channels: Sequence[int]) -> UNet:
    strides = tuple(2 for _ in range(len(channels) - 1))
    return UNet(
        spatial_dims=3,
        in_channels=1,
        out_channels=classes,
        channels=tuple(int(item) for item in channels),
        strides=strides,
        num_res_units=1,
        norm="batch",
    )


def _metric_for_class(prediction: np.ndarray, reference: np.ndarray, label: int) -> dict[str, float | int | None]:
    predicted = prediction == label
    expected = reference == label
    intersection = int(np.logical_and(predicted, expected).sum())
    predicted_count = int(predicted.sum())
    reference_count = int(expected.sum())
    denominator = predicted_count + reference_count
    union = predicted_count + reference_count - intersection
    return {
        "reference_voxels": reference_count,
        "predicted_voxels": predicted_count,
        "dice": None if denominator == 0 else float(2 * intersection / denominator),
        "iou": None if union == 0 else float(intersection / union),
    }


def _summarize_case_metrics(cases: list[dict[str, Any]], labels: list[dict[str, Any]]) -> dict[str, Any]:
    foreground = labels[1:]
    per_class = []
    for label in foreground:
        values = [case["classes"][str(label["id"])] for case in cases]
        dice = [item["dice"] for item in values if item["dice"] is not None]
        iou = [item["iou"] for item in values if item["iou"] is not None]
        per_class.append(
            {
                "id": int(label["id"]),
                "name": label["name"],
                "scored_cases": len(dice),
                "reference_positive_cases": sum(item["reference_voxels"] > 0 for item in values),
                "mean_case_dice": float(np.mean(dice)) if dice else None,
                "mean_case_iou": float(np.mean(iou)) if iou else None,
            }
        )
    case_macro_dice = [case["macro_foreground_dice"] for case in cases if case["macro_foreground_dice"] is not None]
    case_macro_iou = [case["macro_foreground_iou"] for case in cases if case["macro_foreground_iou"] is not None]
    return {
        "case_count": len(cases),
        "aggregation": "unweighted mean of case-level metrics; both-empty class/case pairs are undefined and excluded",
        "mean_case_macro_foreground_dice": float(np.mean(case_macro_dice)) if case_macro_dice else None,
        "mean_case_macro_foreground_iou": float(np.mean(case_macro_iou)) if case_macro_iou else None,
        "per_class": per_class,
        "cases": cases,
    }


@torch.no_grad()
def evaluate_cases(
    model: torch.nn.Module,
    cases: list[dict[str, Any]],
    root: Path,
    labels: list[dict[str, Any]],
    patch_size: Sequence[int],
    dev: torch.device,
    *,
    amp: bool,
    prediction_dir: Path | None = None,
) -> dict[str, Any]:
    model.eval()
    metrics = []
    if prediction_dir is not None:
        prediction_dir.mkdir(parents=True, exist_ok=True)
    for case in cases:
        image, reference, image_nii = _load_case(case, root)
        tensor = torch.from_numpy(_normalise(image)[None, None]).to(dev)
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=amp):
            logits = sliding_window_inference(
                tensor,
                roi_size=tuple(int(item) for item in patch_size),
                sw_batch_size=1,
                predictor=model,
                overlap=0.25,
                mode="constant",
            )
        prediction = logits.float().argmax(1)[0].cpu().numpy().astype(np.uint16)
        class_metrics = {
            str(label["id"]): _metric_for_class(prediction, reference, int(label["id"]))
            for label in labels[1:]
        }
        defined_dice = [item["dice"] for item in class_metrics.values() if item["dice"] is not None]
        defined_iou = [item["iou"] for item in class_metrics.values() if item["iou"] is not None]
        metrics.append(
            {
                "case_id": case["case_id"],
                "patient_id": case["patient_id"],
                "classes": class_metrics,
                "macro_foreground_dice": float(np.mean(defined_dice)) if defined_dice else None,
                "macro_foreground_iou": float(np.mean(defined_iou)) if defined_iou else None,
            }
        )
        if prediction_dir is not None:
            safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(case["case_id"]))
            header = image_nii.header.copy()
            header.set_data_dtype(np.uint16)
            nib.save(nib.Nifti1Image(prediction, image_nii.affine, header), str(prediction_dir / f"{safe_id}.nii.gz"))
    return _summarize_case_metrics(metrics, labels)


def _checkpoint_payload(
    *,
    model: torch.nn.Module,
    optimizer: torch.optim.Optimizer,
    epoch: int,
    best_epoch: int,
    best_score: float,
    best_state: dict[str, torch.Tensor],
    manifest: dict[str, Any],
    config: TrainConfig,
) -> dict[str, Any]:
    return {
        "kind": "volumetric_semantic_segmenter",
        "trainer_version": TRAINER_VERSION,
        "epoch": epoch,
        "best_epoch": best_epoch,
        "best_validation_mean_case_dice": best_score,
        "state_dict": model.state_dict(),
        "best_state_dict": best_state,
        "optimizer_state_dict": optimizer.state_dict(),
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "manifest_sha256": sha256_file(config.manifest_path),
        "labels": manifest["labels"],
        "architecture": {
            "name": "monai.networks.nets.UNet",
            "spatial_dims": 3,
            "in_channels": 1,
            "out_channels": len(manifest["labels"]),
            "channels": list(config.channels),
            "strides": [2] * (len(config.channels) - 1),
            "num_res_units": 1,
        },
        "preprocessing_version": PREPROCESSING_VERSION,
        "patch_size": list(config.patch_size),
        "seed": config.seed,
    }


def run_training(config: TrainConfig) -> dict[str, Any]:
    """Execute training and held-out evaluation after all fail-closed gates pass."""

    manifest = json.loads(config.manifest_path.read_text(encoding="utf-8"))
    # This must precede validate_manifest: a blocked real-data run must not load
    # even one patient image while attempting to train.
    license_evidence = enforce_training_license(
        manifest,
        config.registry_path,
        allow_synthetic_test_fixture=config.allow_synthetic_test_fixture,
    )
    validation = validate_manifest(manifest, verify_hashes=True)

    if config.epochs < 1 or config.batch_size < 1 or config.patches_per_case < 1:
        raise ValueError("epochs, batch_size and patches_per_case must be positive")
    if len(config.channels) < 2 or any(channel < 1 for channel in config.channels):
        raise ValueError("channels must contain at least two positive widths")
    divisor = 2 ** (len(config.channels) - 1)
    if any(size < divisor or size % divisor for size in config.patch_size):
        raise ValueError(f"Every patch dimension must be a positive multiple of {divisor}.")

    dev = _resolve_device(config.device)
    amp_effective = bool(config.amp and dev.type == "cuda")
    if config.torch_threads is not None:
        torch.set_num_threads(config.torch_threads)
    set_seed(config.seed)
    # CUDA cross-entropy (nll_loss) has no deterministic kernel, so strict mode would refuse
    # the first training step; on CUDA nondeterministic kernels warn instead (recorded below).
    torch.use_deterministic_algorithms(True, warn_only=dev.type == "cuda")
    determinism = ("strict" if dev.type != "cuda" else
                   "warn_only: CUDA nll_loss has no deterministic kernel; repeated CUDA runs can differ slightly")
    if dev.type == "cuda":
        torch.backends.cudnn.benchmark = False
        torch.backends.cudnn.deterministic = True

    root = Path(manifest["dataset_root"])
    splits = {split: [case for case in manifest["cases"] if case["split"] == split] for split in ("train", "val", "test")}
    model = _build_model(len(manifest["labels"]), config.channels).to(dev)
    optimizer = torch.optim.AdamW(model.parameters(), lr=config.learning_rate, weight_decay=config.weight_decay)
    loss_function = DiceCELoss(to_onehot_y=True, softmax=True)
    scaler = torch.amp.GradScaler("cuda", enabled=amp_effective)
    start_epoch = 1
    best_epoch = 0
    best_score = -1.0
    best_state: dict[str, torch.Tensor] = copy.deepcopy({key: value.detach().cpu() for key, value in model.state_dict().items()})
    resume_evidence = None
    if config.resume is not None:
        checkpoint = torch.load(config.resume, map_location=dev, weights_only=False)
        if checkpoint.get("dataset_version") != manifest["dataset_version"]:
            raise ValueError("Resume checkpoint dataset_version does not match the manifest.")
        if checkpoint.get("labels") != manifest["labels"]:
            raise ValueError("Resume checkpoint labels do not match the manifest.")
        model.load_state_dict(checkpoint["state_dict"])
        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        start_epoch = int(checkpoint["epoch"]) + 1
        best_epoch = int(checkpoint.get("best_epoch") or 0)
        best_score = float(checkpoint.get("best_validation_mean_case_dice", -1.0))
        best_state = {key: value.detach().cpu() for key, value in checkpoint.get("best_state_dict", checkpoint["state_dict"]).items()}
        resume_evidence = {"path": str(config.resume.resolve()), "sha256": sha256_file(config.resume), "from_epoch": int(checkpoint["epoch"])}

    config.output_dir.mkdir(parents=True, exist_ok=True)
    execution_path = config.output_dir / "execution.json"
    execution = {
        "execution_status": "RUNNING",
        "trainer_version": TRAINER_VERSION,
        "manifest_path": str(config.manifest_path.resolve()),
        "manifest_sha256": sha256_file(config.manifest_path),
        "dataset_id": manifest["dataset_id"],
        "dataset_version": manifest["dataset_version"],
        "synthetic_test_fixture": manifest["synthetic_test_fixture"],
        "license_gate": license_evidence,
        "manifest_validation": validation,
        "environment": environment(),
        "git": git_revision(),
        "config": {
            "epochs": config.epochs,
            "batch_size": config.batch_size,
            "learning_rate": config.learning_rate,
            "weight_decay": config.weight_decay,
            "patch_size": list(config.patch_size),
            "channels": list(config.channels),
            "patches_per_case": config.patches_per_case,
            "workers": config.workers,
            "seed": config.seed,
            "device_requested": config.device,
            "device_effective": dev.type,
            "amp_requested": config.amp,
            "amp_effective": amp_effective,
            "deterministic_algorithms": determinism,
            "preprocessing_version": PREPROCESSING_VERSION,
        },
        "resume": resume_evidence,
        "epochs": [],
        "model_registry_mutation": "NONE",
    }
    execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")

    dataset = PatchDataset(
        splits["train"], root, config.patch_size, config.patches_per_case, config.seed
    )
    last_checkpoint = config.output_dir / "last.pt"
    best_checkpoint = config.output_dir / "best.pt"
    if config.resume is not None and start_epoch > config.epochs:
        raise ValueError(
            f"Resume checkpoint is already at epoch {start_epoch - 1}; --epochs must request at least epoch {start_epoch}."
        )
    if config.resume is not None:
        # Materialize the inherited best state in the new run directory even
        # when later epochs do not improve it.
        inherited = _checkpoint_payload(
            model=model,
            optimizer=optimizer,
            epoch=start_epoch - 1,
            best_epoch=best_epoch,
            best_score=best_score,
            best_state=best_state,
            manifest=manifest,
            config=config,
        )
        torch.save({**inherited, "state_dict": best_state}, best_checkpoint)
    for epoch in range(start_epoch, config.epochs + 1):
        dataset.set_epoch(epoch)
        generator = torch.Generator().manual_seed(config.seed + epoch)
        loader = DataLoader(
            dataset,
            batch_size=config.batch_size,
            shuffle=True,
            num_workers=config.workers,
            worker_init_fn=seed_worker,
            generator=generator,
            persistent_workers=config.workers > 0,
        )
        model.train()
        losses = []
        for images, masks in loader:
            images = images.to(dev, non_blocking=True)
            masks = masks.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=amp_effective):
                loss = loss_function(model(images).float(), masks)
            scaler.scale(loss).backward()
            scaler.step(optimizer)
            scaler.update()
            losses.append(float(loss.detach().cpu()))

        validation_metrics = evaluate_cases(
            model,
            splits["val"],
            root,
            manifest["labels"],
            config.patch_size,
            dev,
            amp=amp_effective,
        )
        score = validation_metrics["mean_case_macro_foreground_dice"]
        comparable_score = float(score) if score is not None else -1.0
        if comparable_score > best_score:
            best_score = comparable_score
            best_epoch = epoch
            best_state = copy.deepcopy({key: value.detach().cpu() for key, value in model.state_dict().items()})
        epoch_record = {
            "epoch": epoch,
            "mean_train_loss": float(np.mean(losses)),
            "validation_mean_case_macro_foreground_dice": score,
        }
        execution["epochs"].append(epoch_record)
        payload = _checkpoint_payload(
            model=model,
            optimizer=optimizer,
            epoch=epoch,
            best_epoch=best_epoch,
            best_score=best_score,
            best_state=best_state,
            manifest=manifest,
            config=config,
        )
        torch.save(payload, last_checkpoint)
        if best_epoch == epoch:
            torch.save({**payload, "state_dict": best_state}, best_checkpoint)
        execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")

    model.load_state_dict(best_state)
    prediction_dir = config.output_dir / "held_out_predictions" if config.save_predictions else None
    held_out = evaluate_cases(
        model,
        splits["test"],
        root,
        manifest["labels"],
        config.patch_size,
        dev,
        amp=amp_effective,
        prediction_dir=prediction_dir,
    )
    execution.update(
        {
            "execution_status": "COMPLETE",
            "selection": {
                "criterion": "validation mean of case-level macro foreground Dice",
                "best_epoch": best_epoch,
                "best_score": best_score,
            },
            "held_out_test": held_out,
            "checkpoint": {
                "path": str(best_checkpoint.resolve()),
                "sha256": sha256_file(best_checkpoint),
                "last_path": str(last_checkpoint.resolve()),
                "last_sha256": sha256_file(last_checkpoint),
            },
            "held_out_predictions": None if prediction_dir is None else str(prediction_dir.resolve()),
            "model_registry_mutation": "NONE",
            "registry_claim": "No registry-ready or validated status is emitted by this trainer.",
        }
    )
    execution_path.write_text(json.dumps(execution, indent=2) + "\n", encoding="utf-8")
    return execution


def create_synthetic_fixture(work_dir: Path, *, seed: int = 20261024) -> Path:
    """Create small, deterministic NIfTI pairs for an isolated execution test."""

    if work_dir.exists() and any(work_dir.iterdir()):
        raise ValueError("Synthetic smoke work directory must be empty to avoid overwriting files.")
    data_root = work_dir / "fixture"
    data_root.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(seed)
    pairs = []
    grid = np.indices((12, 12, 12))
    for index in range(6):
        patient_id = f"synthetic_patient_{index:02d}"
        case_id = f"{patient_id}_case"
        mask = np.zeros((12, 12, 12), dtype=np.uint8)
        # Every patient has a distinct spatial mask so the same leakage check
        # used for real data can remain strict in the fixture.
        first = (grid[0] - (3 + index)) ** 2 + (grid[1] - 4) ** 2 + (grid[2] - 4) ** 2 <= 5
        second = (grid[0] - 8) ** 2 + (grid[1] - (9 - index)) ** 2 + (grid[2] - 8) ** 2 <= 4
        mask[first] = 1
        mask[second] = 2
        image = rng.normal(0, 0.05, mask.shape).astype(np.float32)
        image += (mask == 1).astype(np.float32) * 1.5
        image += (mask == 2).astype(np.float32) * 3.0
        affine = np.diag([1.25, 1.25, 2.5, 1.0])
        image_name = f"{case_id}_image.nii.gz"
        mask_name = f"{case_id}_mask.nii.gz"
        nib.save(nib.Nifti1Image(image, affine), str(data_root / image_name))
        nib.save(nib.Nifti1Image(mask, affine), str(data_root / mask_name))
        pairs.append(
            {
                "patient_id": patient_id,
                "case_id": case_id,
                "image_path": image_name,
                "mask_path": mask_name,
            }
        )
    manifest = build_manifest(
        dataset_id="synthetic-volumetric-fixture",
        dataset_root=data_root,
        pairs=pairs,
        labels={0: "background", 1: "fixture_region_a", 2: "fixture_region_b"},
        seed=seed,
        val_fraction=1 / 6,
        test_fraction=1 / 6,
        discovery={"layout": "GENERATED_SYNTHETIC_TEST_FIXTURE", "generator": TRAINER_VERSION},
        synthetic_test_fixture=True,
    )
    return write_manifest(manifest, work_dir / "manifest.json")


def _training_config_from_args(args: argparse.Namespace, *, synthetic: bool = False) -> TrainConfig:
    return TrainConfig(
        manifest_path=args.manifest,
        output_dir=args.output_dir,
        registry_path=args.registry,
        device=args.device,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.learning_rate,
        weight_decay=args.weight_decay,
        patch_size=tuple(args.patch_size),
        channels=tuple(args.channels),
        patches_per_case=args.patches_per_case,
        workers=args.workers,
        seed=args.seed,
        amp=args.amp,
        resume=args.resume,
        save_predictions=args.save_predictions,
        torch_threads=args.torch_threads,
        allow_synthetic_test_fixture=synthetic,
    )


def _add_training_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--registry", type=Path, default=DEFAULT_REGISTRY)
    parser.add_argument("--device", choices=("auto", "cpu", "cuda"), default="auto")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=2)
    parser.add_argument("--learning-rate", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-5)
    parser.add_argument("--patch-size", type=int, nargs=3, default=(96, 96, 32), metavar=("X", "Y", "Z"))
    parser.add_argument("--channels", type=int, nargs="+", default=(16, 32, 64, 128))
    parser.add_argument("--patches-per-case", type=int, default=2)
    parser.add_argument("--workers", type=int, default=0)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--amp", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--resume", type=Path)
    parser.add_argument("--save-predictions", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--torch-threads", type=int)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    subparsers = parser.add_subparsers(dest="command", required=True)
    train = subparsers.add_parser("train", help="Run a registry-authorized real-data training job.")
    _add_training_arguments(train)
    smoke = subparsers.add_parser("smoke", help="Generate and execute an isolated synthetic CPU smoke run.")
    smoke.add_argument("--work-dir", type=Path, required=True)
    smoke.add_argument("--seed", type=int, default=20261024)

    args = parser.parse_args(argv)
    if args.command == "smoke":
        args.manifest = create_synthetic_fixture(args.work_dir, seed=args.seed)
        args.output_dir = args.work_dir / "run"
        args.registry = DEFAULT_REGISTRY
        args.device = "cpu"
        args.epochs = 1
        args.batch_size = 2
        args.learning_rate = 1e-3
        args.weight_decay = 1e-5
        args.patch_size = (12, 12, 12)
        args.channels = (4, 8)
        args.patches_per_case = 1
        args.workers = 0
        args.amp = False
        args.resume = None
        args.save_predictions = True
        args.torch_threads = 1
        config = _training_config_from_args(args, synthetic=True)
    else:
        config = _training_config_from_args(args)
    result = run_training(config)
    print(
        json.dumps(
            {
                "execution_status": result["execution_status"],
                "dataset_id": result["dataset_id"],
                "synthetic_test_fixture": result["synthetic_test_fixture"],
                "best_epoch": result["selection"]["best_epoch"],
                "held_out_cases": result["held_out_test"]["case_count"],
                "checkpoint_sha256": result["checkpoint"]["sha256"],
                "model_registry_mutation": result["model_registry_mutation"],
            },
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
