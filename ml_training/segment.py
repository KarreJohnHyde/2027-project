"""2D semantic segmentation (MONAI U-Net) of COCO-polygon datasets with publisher splits.

Protocol: masks are rasterised from the publisher's COCO polygons; the model is
trained on the train split and the epoch with the best validation mean
foreground Dice is kept; the frozen checkpoint is evaluated once on the test
split (and on the test images without a confirmed cross-split near-duplicate).
Dice/IoU follow the validation kit's empty-mask convention.

    python -m ml_training.segment --task-id arcade-syntax-segmentation --model-id angiography_syntax_segmenter ...
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
import torch
from monai.losses import DiceCELoss
from monai.networks.nets import UNet
from PIL import Image
from pycocotools import mask as coco_mask
from torch.utils.data import DataLoader, Dataset
from torchvision.transforms import InterpolationMode
from torchvision.transforms import functional as TF

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, cross_split_component_summary, device, read_samples, register_model, relative, seed_worker, set_seed

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import _surface_distances  # noqa: E402  (same distances as the Validation Center)


BINARY_MASK_THRESHOLD = 127  # publisher masks saved as JPEG carry compression noise around the edge


def build_binary_masks(rows: list[dict], cache: Path, class_name: str) -> tuple[list[str], list[dict]]:
    """Single-class masks from publisher mask images (white = class), cached as class-index PNG."""
    cache.mkdir(parents=True, exist_ok=True)
    items = []
    for row in rows:
        target = cache / f"{row['split']}_{row['image_id']}.png"
        if not target.exists():
            with Image.open(row["mask_file"]) as mask_image, Image.open(row["path"]) as image:
                if mask_image.size != image.size:
                    raise ValueError(f"mask and image sizes differ for {row['image_id']}")
                mask = (np.asarray(mask_image.convert("L")) > BINARY_MASK_THRESHOLD).astype(np.uint8)
            Image.fromarray(mask).save(target)
        items.append({**row, "mask_path": str(target)})
    return [class_name], items


def build_masks(rows: list[dict], cache: Path) -> tuple[list[str], list[dict]]:
    """Class-index masks (0 = background) cached as PNG; returns class names in id order."""
    cache.mkdir(parents=True, exist_ok=True)
    categories: dict[int, str] = {}
    by_file: dict[str, dict] = {}
    for row in rows:
        if row["annotation_file"] not in by_file:
            data = json.loads(Path(row["annotation_file"]).read_text(encoding="utf-8"))
            categories.update({item["id"]: item["name"] for item in data["categories"]})
            grouped: dict[int, list] = {}
            for annotation in data["annotations"]:
                grouped.setdefault(annotation["image_id"], []).append(annotation)
            by_file[row["annotation_file"]] = grouped
    used = sorted({a["category_id"] for grouped in by_file.values() for anns in grouped.values() for a in anns})
    index = {category: position + 1 for position, category in enumerate(used)}
    items = []
    for row in rows:
        target = cache / f"{row['split']}_{row['image_id']}.png"
        with Image.open(row["path"]) as image:
            width, height = image.size
        if not target.exists():
            mask = np.zeros((height, width), dtype=np.uint8)
            for annotation in sorted(by_file[row["annotation_file"]].get(int(row["image_id"]), []), key=lambda a: a["area"], reverse=True):
                polygons = [p for p in annotation["segmentation"] if len(p) >= 6] if isinstance(annotation["segmentation"], list) else []
                if not polygons:
                    continue
                rle = coco_mask.merge(coco_mask.frPyObjects(polygons, height, width))
                mask[coco_mask.decode(rle) > 0] = index[annotation["category_id"]]
            Image.fromarray(mask).save(target)
        items.append({**row, "mask_path": str(target)})
    return [categories[category] for category in used], items


def standardise(tensor: torch.Tensor) -> torch.Tensor:
    """Per-image, per-channel standardisation (the inference adapter applies the same)."""
    mean = tensor.mean(dim=(1, 2), keepdim=True)
    std = tensor.std(dim=(1, 2), keepdim=True)
    return (tensor - mean) / (std + 1e-6)


class SegmentationSet(Dataset):
    def __init__(self, items: list[dict], size: int, train: bool, rgb: bool = False):
        self.items, self.size, self.train, self.mode = items, size, train, "RGB" if rgb else "L"

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, position: int):
        item = self.items[position]
        with Image.open(item["path"]) as image:
            # Materialise the resized images before their source file handles are
            # closed. PIL transformations can otherwise retain a lazy reference
            # to ``image.fp`` and fail later in DataLoader workers during affine
            # augmentation.
            picture = TF.resize(image.convert(self.mode), [self.size, self.size], interpolation=InterpolationMode.BILINEAR).copy()
        with Image.open(item["mask_path"]) as image:
            mask = TF.resize(image, [self.size, self.size], interpolation=InterpolationMode.NEAREST).copy()
        if self.train:
            angle = float(np.random.uniform(-10, 10))
            scale = float(np.random.uniform(0.9, 1.1))
            picture = TF.affine(picture, angle=angle, translate=[0, 0], scale=scale, shear=[0.0], interpolation=InterpolationMode.BILINEAR)
            mask = TF.affine(mask, angle=angle, translate=[0, 0], scale=scale, shear=[0.0], interpolation=InterpolationMode.NEAREST)
            picture = TF.adjust_contrast(TF.adjust_brightness(picture, float(np.random.uniform(0.9, 1.1))), float(np.random.uniform(0.9, 1.1)))
        tensor = TF.to_tensor(picture)
        # Grayscale keeps the original whole-image standardisation (one channel: identical).
        tensor = standardise(tensor) if self.mode == "RGB" else (tensor - tensor.mean()) / (tensor.std() + 1e-6)
        return tensor, torch.from_numpy(np.asarray(mask, dtype=np.int64))[None]


def per_image_scores(prediction: np.ndarray, reference: np.ndarray, classes: int) -> dict:
    """Dice per class with the kit's convention (both empty -> not counted for that class)."""
    dice = {}
    for k in range(1, classes + 1):
        p, r = prediction == k, reference == k
        if not p.any() and not r.any():
            continue
        dice[k] = 2 * np.logical_and(p, r).sum() / (p.sum() + r.sum())
    vessel_p, vessel_r = prediction > 0, reference > 0
    total = vessel_p.sum() + vessel_r.sum()
    vessel_dice = 2 * np.logical_and(vessel_p, vessel_r).sum() / total if total else 1.0
    union = np.logical_or(vessel_p, vessel_r).sum()
    vessel_iou = np.logical_and(vessel_p, vessel_r).sum() / union if union else 1.0
    return {"dice": dice, "vessel_dice": float(vessel_dice), "vessel_iou": float(vessel_iou)}


@torch.no_grad()
def predict_masks(model, loader, dev) -> list[np.ndarray]:
    model.eval()
    outputs = []
    for images, _masks in loader:
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            logits = model(images.to(dev))
        outputs.extend(logits.float().argmax(1).cpu().numpy().astype(np.uint8))
    return outputs


def references(items: list[dict], size: int) -> list[np.ndarray]:
    result = []
    for item in items:
        with Image.open(item["mask_path"]) as image:
            result.append(np.asarray(TF.resize(image, [size, size], interpolation=InterpolationMode.NEAREST), dtype=np.uint8))
    return result


def summarise(predictions, refs, classes: int, names: list[str], groups: np.ndarray | None) -> dict:
    scores = [per_image_scores(p, r, classes) for p, r in zip(predictions, refs)]
    per_class = []
    for k in range(1, classes + 1):
        values = [s["dice"][k] for s in scores if k in s["dice"]]
        per_class.append({"segment": names[k - 1], "images": len(values), "mean_dice": float(np.mean(values)) if values else None})
    image_means = np.array([np.mean(list(s["dice"].values())) if s["dice"] else 1.0 for s in scores])
    vessel = np.array([s["vessel_dice"] for s in scores])
    distances = [_surface_distances(r > 0, p > 0, (1.0, 1.0)) for p, r in zip(predictions, refs)]
    hd95 = [d["hausdorff_95"] for d in distances if d]
    defined = [item["mean_dice"] for item in per_class if item["mean_dice"] is not None]
    result = {
        "n_images": len(scores), "mean_foreground_dice_per_image": float(image_means.mean()), "macro_segment_dice": float(np.mean(defined)) if defined else None,
        "vessel_dice": float(vessel.mean()), "vessel_iou": float(np.mean([s["vessel_iou"] for s in scores])),
        "vessel_hd95_px_at_model_resolution": float(np.mean(hd95)) if hd95 else None, "per_segment": per_class,
    }
    if groups is not None:
        result["confidence_intervals_95"] = {
            "mean_foreground_dice_per_image": bootstrap_ci(lambda idx: float(image_means[idx].mean()), len(scores), groups),
            "vessel_dice": bootstrap_ci(lambda idx: float(vessel[idx].mean()), len(scores), groups),
        }
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--modality", required=True)
    parser.add_argument("--anatomy", required=True)
    parser.add_argument("--size", type=int, default=512)
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=8)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261024)
    parser.add_argument("--rgb", action="store_true", help="Three-channel input (colour carries signal, e.g. endoscopy).")
    parser.add_argument("--foreground-label", default="vessel", help="Name of the union of all classes in reports (e.g. polyp).")
    args = parser.parse_args()

    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    dataset, task = next((d, t) for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == args.task_id)
    if not task["training_eligible"]:
        raise SystemExit(f"{args.task_id} is not training-eligible: {task['flags']}")
    prep = task["preparation"]
    rows = read_samples(Path(prep["sample_manifest"]))
    cache = ROOT / "_derived" / "datasets" / args.task_id / "masks"
    binary = "mask_file" in rows[0]
    names, items = build_binary_masks(rows, cache, task.get("class_name", args.foreground_label)) if binary else build_masks(rows, cache)
    classes = len(names)
    channels = 3 if args.rgb else 1
    splits = {split: [item for item in items if item["split"] == split] for split in ("train", "val", "test")}
    set_seed(args.seed)
    dev = device()
    run = Run(args.model_id, args.task_id, {**vars(args), "classes": names, "dataset_version": prep["dataset_version"]})
    model = UNet(spatial_dims=2, in_channels=channels, out_channels=classes + 1, channels=(32, 64, 128, 256, 512), strides=(2, 2, 2, 2), num_res_units=2, norm="batch").to(dev)
    loader = DataLoader(SegmentationSet(splits["train"], args.size, train=True, rgb=args.rgb), batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
                        worker_init_fn=seed_worker, generator=torch.Generator().manual_seed(args.seed), persistent_workers=args.workers > 0, drop_last=True)
    val_loader = DataLoader(SegmentationSet(splits["val"], args.size, train=False, rgb=args.rgb), batch_size=args.batch_size, num_workers=args.workers)
    val_refs = references(splits["val"], args.size)
    loss_function = DiceCELoss(to_onehot_y=True, softmax=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=args.epochs * len(loader), pct_start=0.1)
    best_state, best_dice, best_epoch = None, -1.0, -1
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for images, masks in loader:
            images, masks = images.to(dev, non_blocking=True), masks.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                loss = loss_function(model(images).float(), masks)
            loss.backward()
            optimizer.step()
            scheduler.step()
            running += loss.item()
        if epoch % 2 == 0 or epoch == args.epochs:
            summary = summarise(predict_masks(model, val_loader, dev), val_refs, classes, names, None)
            dice = summary["mean_foreground_dice_per_image"]
            run.log(epoch=epoch, train_loss=round(running / len(loader), 4), val_mean_dice=round(dice, 4), val_vessel_dice=round(summary["vessel_dice"], 4),
                    gpu_peak_mib=int(torch.cuda.max_memory_allocated() / 2**20) if dev.type == "cuda" else None)
            if dice > best_dice:
                best_state, best_dice, best_epoch = copy.deepcopy({k: v.cpu() for k, v in model.state_dict().items()}), dice, epoch
    model.load_state_dict(best_state)

    # Test split, evaluated once with the frozen checkpoint.
    test_loader = DataLoader(SegmentationSet(splits["test"], args.size, train=False, rgb=args.rgb), batch_size=args.batch_size, num_workers=args.workers)
    predictions = predict_masks(model, test_loader, dev)
    refs = references(splits["test"], args.size)
    groups = np.array([item["group_id"] for item in splits["test"]])
    full = summarise(predictions, refs, classes, names, groups)
    component_leakage = cross_split_component_summary(items)
    crossing_groups = component_leakage.pop("group_ids")
    keep = [i for i, item in enumerate(splits["test"]) if str(item.get("group_id", "")).strip() not in crossing_groups]
    filtered = summarise([predictions[i] for i in keep], [refs[i] for i in keep], classes, names, None)
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "semantic_segmenter", "arch": "monai.networks.nets.UNet",
        "arch_params": {"spatial_dims": 2, "in_channels": channels, "out_channels": classes + 1, "channels": [32, 64, 128, 256, 512], "strides": [2, 2, 2, 2], "num_res_units": 2, "norm": "batch"},
        "state_dict": best_state, "classes": names, "input_size": args.size, "task_id": args.task_id, "dataset_version": prep["dataset_version"],
        "color": "rgb" if args.rgb else "gray", "foreground_label": args.foreground_label,
        "preprocessing": ("RGB; per-channel" if args.rgb else "grayscale; per-image") + " standardisation after bilinear resize to input_size; masks resized back to source size with nearest neighbour",
    })
    prediction_dir = run.directory / "test_masks"
    prediction_dir.mkdir(exist_ok=True)
    for item, mask in zip(splits["test"], predictions):
        Image.fromarray(mask).save(prediction_dir / f"{item['image_id']}.png")
    absent_test_segments = [item["segment"] for item in full["per_segment"] if item["images"] == 0]
    rare_test_segments = [item["segment"] for item in full["per_segment"] if 0 < item["images"] < 20]
    limitations = [
        f"Evaluated at the model's {args.size}x{args.size} working resolution; distances are in those pixels, not millimetres.",
        "The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.",
        "Internal test split from the same source; no external validation.",
        "Research-only output; not validated for clinical use.",
    ]
    if absent_test_segments:
        limitations.append(f"No held-out reference mask exists for segment(s) {', '.join(absent_test_segments)}; their per-segment Dice is undefined.")
    if rare_test_segments:
        limitations.append(f"Held-out support is below 20 images for segment(s) {', '.join(rare_test_segments)}; their per-segment estimates are unstable.")
    report = {
        "model_id": args.model_id, "run_id": run.run_id, "task_id": args.task_id, "dataset": dataset["title"], "dataset_id": dataset["id"],
        "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"], "split_method": prep["split_method"], "split_counts": prep["per_split"],
        "leakage_check": {
            **{key: prep.get(key) for key in ("near_duplicate_groups_crossing_splits", "images_in_crossing_groups", "test_images_with_cross_split_duplicate", "confirmation")},
            **component_leakage,
        },
        "classes": names, "foreground_label": args.foreground_label, "input_color": "rgb" if args.rgb else "gray",
        "selection": {"criterion": "validation mean foreground Dice per image", "best_epoch": best_epoch, "val_mean_dice": best_dice},
        "test": full, "test_without_cross_split_duplicates": filtered, "evaluated_at_resolution": f"{args.size}x{args.size}",
        "empty_mask_convention": f"A segment absent from both prediction and reference is not scored for that image; whole-{args.foreground_label} Dice uses Dice = 1 when both are empty.",
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(prediction_dir),
        "training_seconds": run.elapsed_seconds, "config": vars(args),
        "reporting_context": {"dataset": dataset["title"], "dataset_version": prep["dataset_version"][:16], "split": "test", "checkpoint": f"sha256:{checkpoint_sha}"},
        "limitations": limitations,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def ci(block: dict, name: str) -> str:
        interval = block.get("confidence_intervals_95", {}).get(name, {})
        return f"{interval['low']:.3f}-{interval['high']:.3f}" if interval.get("status") == "COMPUTED" else "not computed"

    card = [
        f"# Model card: {args.display_name}", "",
        f"- **Model id:** `{args.model_id}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Task:** {task['target']} ({classes} segment classes + background)",
        f"- **Data:** {dataset['title']} ({dataset['license']['name']}; {dataset['license']['source']}); dataset version `{prep['dataset_version'][:16]}`; {prep['split_method']}.",
        f"- **Architecture:** MONAI 2D U-Net (32-512 channels, residual units), trained from scratch; best validation epoch {best_epoch}.",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.",
        "", "## Held-out test results (internal, evaluated once)", "",
        f"- Mean foreground Dice per image {full['mean_foreground_dice_per_image']:.3f} (95% CI {ci(full, 'mean_foreground_dice_per_image')}); macro segment Dice {full['macro_segment_dice'] or 0:.3f}.",
        f"- Whole-{args.foreground_label} Dice {full['vessel_dice']:.3f} (95% CI {ci(full, 'vessel_dice')}), IoU {full['vessel_iou']:.3f}, HD95 {full['vessel_hd95_px_at_model_resolution'] or 0:.1f} px at {args.size} px.",
        f"- Without test images that have a near-duplicate in another split (n = {filtered['n_images']}): mean Dice {filtered['mean_foreground_dice_per_image']:.3f}.",
        "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", f"Full report: `{relative(report_path)}`.",
    ]
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    (MODEL_CARDS / f"{args.model_id}.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    register_model({
        "model_id": args.model_id, "display_name": args.display_name, "domain": "medical_imaging", "task": "semantic_segmentation",
        "anatomy": args.anatomy, "framework": "MONAI UNet 2D", "adapter": "app.services.model_inference", "source_repository": "medtwin/ml_training",
        "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path), "device": "cuda_or_cpu",
        "supported_inputs": ["image/png", "image/jpeg"], "supported_modalities": [args.modality], "supported_classes": names,
        "status": "READY_UNVALIDATED", "validated": False, "research_inference": True, "limitations": report["limitations"],
        "artifact_bundle": {
            "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"]["name"], "split_manifest_path": relative(Path(prep["sample_manifest"])),
            "task_definition": task["target"],
            "label_definition": {"source": f"publisher binary masks thresholded at {BINARY_MASK_THRESHOLD}" if binary else "COCO polygons rasterised to class indices", "classes": names},
            "preprocessing_version": f"{'rgb' if args.rgb else 'gray'}-resize{args.size}-standardise-v1", "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha,
            "calibration": None, "decision_thresholds": {"rule": "argmax over softmax per pixel"}, "abstention_thresholds": None,
            "held_out_predictions_path": checkpoint_ref(prediction_dir), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(MODEL_CARDS / f"{args.model_id}.md"),
        },
    })
    run.log(event="done", test_mean_dice=full["mean_foreground_dice_per_image"], test_vessel_dice=full["vessel_dice"], checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
