"""Object detection (Faster R-CNN, ResNet-50 FPN v2) on publisher-split datasets.

Protocol: train on the train split; select the epoch with the best validation
AP50 (pycocotools COCOeval, the Validation Center's evaluator); choose the display
score threshold on validation (maximum F1 at IoU 0.5); evaluate the frozen
checkpoint once on the test split, and again on the test images that have no
confirmed near-duplicate in another split. Boxes are predicted in the original
image's pixel coordinates.

    python -m ml_training.detect --task-id arcade-stenosis-detection --model-id angiography_stenosis_detector ...
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch.utils.data import DataLoader, Dataset
from torchvision.models.detection import FasterRCNN_ResNet50_FPN_V2_Weights, fasterrcnn_resnet50_fpn_v2
from torchvision.models.detection.faster_rcnn import FastRCNNPredictor
from torchvision.transforms import functional as F

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, checkpoint_ref, cross_split_component_summary, device, read_samples, register_model, relative, seed_worker, set_seed

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import evaluate_detection  # noqa: E402  (same evaluator as the Validation Center)


def load_targets(rows: list[dict], label_format: str, category: str | None) -> list[dict]:
    """Per image: path, width, height and boxes [x1, y1, x2, y2] in pixels."""
    annotations_by_file: dict[str, dict] = {}
    items = []
    for row in rows:
        with Image.open(row["path"]) as image:
            width, height = image.size
        boxes = []
        if label_format == "COCO":
            if row["annotation_file"] not in annotations_by_file:
                data = json.loads(Path(row["annotation_file"]).read_text(encoding="utf-8"))
                names = {item["id"]: item["name"] for item in data["categories"]}
                per_image: dict[int, list] = {}
                for annotation in data["annotations"]:
                    if category is None or names.get(annotation["category_id"]) == category:
                        x, y, w, h = annotation["bbox"]
                        per_image.setdefault(annotation["image_id"], []).append([x, y, x + w, y + h])
                annotations_by_file[row["annotation_file"]] = per_image
            boxes = annotations_by_file[row["annotation_file"]].get(int(row["image_id"]), [])
        else:  # YOLO: class cx cy w h, normalised
            if row["label_file"]:
                for line in Path(row["label_file"]).read_text(encoding="utf-8").splitlines():
                    parts = line.split()
                    if len(parts) == 5:
                        _, cx, cy, w, h = map(float, parts)
                        boxes.append([(cx - w / 2) * width, (cy - h / 2) * height, (cx + w / 2) * width, (cy + h / 2) * height])
        boxes = [[max(0.0, x1), max(0.0, y1), min(float(width), x2), min(float(height), y2)] for x1, y1, x2, y2 in boxes]
        boxes = [box for box in boxes if box[2] - box[0] >= 1 and box[3] - box[1] >= 1]
        items.append({**row, "width": width, "height": height, "boxes": boxes})
    return items


class DetectionSet(Dataset):
    def __init__(self, items: list[dict], train: bool, allow_flip: bool):
        self.items, self.train, self.allow_flip = items, train, allow_flip

    def __len__(self) -> int:
        return len(self.items)

    def __getitem__(self, index: int):
        item = self.items[index]
        with Image.open(item["path"]) as image:
            tensor = F.to_tensor(image.convert("RGB"))
        boxes = torch.tensor(item["boxes"], dtype=torch.float32).reshape(-1, 4)
        if self.train:
            if self.allow_flip and torch.rand(1).item() < 0.5:
                tensor = tensor.flip(-1)
                width = tensor.shape[-1]
                boxes = torch.stack([width - boxes[:, 2], boxes[:, 1], width - boxes[:, 0], boxes[:, 3]], dim=1) if len(boxes) else boxes
            tensor = F.adjust_brightness(tensor, 0.9 + 0.2 * torch.rand(1).item())
            tensor = F.adjust_contrast(tensor, 0.9 + 0.2 * torch.rand(1).item())
        return tensor, {"boxes": boxes, "labels": torch.ones(len(boxes), dtype=torch.int64)}


def collate(batch):
    return tuple(zip(*batch))


def coco_reference(items: list[dict]) -> dict:
    images, annotations = [], []
    for image_id, item in enumerate(items, start=1):
        images.append({"id": image_id, "width": item["width"], "height": item["height"], "file_name": item["entry"]})
        for box in item["boxes"]:
            annotations.append({"id": len(annotations) + 1, "image_id": image_id, "category_id": 1, "iscrowd": 0,
                                "bbox": [box[0], box[1], box[2] - box[0], box[3] - box[1]], "area": (box[2] - box[0]) * (box[3] - box[1])})
    return {"images": images, "annotations": annotations, "categories": [{"id": 1, "name": "target"}]}


@torch.no_grad()
def predict(model, items: list[dict], dev, batch_size: int = 4) -> list[list[dict]]:
    model.eval()
    outputs = []
    for start in range(0, len(items), batch_size):
        tensors = []
        for item in items[start:start + batch_size]:
            with Image.open(item["path"]) as image:
                tensors.append(F.to_tensor(image.convert("RGB")).to(dev))
        for result in model(tensors):
            outputs.append([{"bbox": box.tolist(), "score": float(score)} for box, score in zip(result["boxes"].cpu(), result["scores"].cpu())])
    return outputs


def coco_results(predictions: list[list[dict]]) -> list[dict]:
    results = []
    for image_id, boxes in enumerate(predictions, start=1):
        for item in boxes:
            x1, y1, x2, y2 = item["bbox"]
            results.append({"image_id": image_id, "category_id": 1, "bbox": [x1, y1, x2 - x1, y2 - y1], "score": item["score"]})
    return results


def score(items: list[dict], predictions: list[list[dict]]) -> dict:
    results = coco_results(predictions)
    if not results:
        return {"metrics": {"map_50_95": 0.0, "ap_50": 0.0}, "detections": 0}
    return evaluate_detection(json.dumps(results).encode(), json.dumps(coco_reference(items)).encode())


def iou(a, b) -> float:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    union = (a[2] - a[0]) * (a[3] - a[1]) + (b[2] - b[0]) * (b[3] - b[1]) - inter
    return inter / union if union else 0.0


def operating_point(items: list[dict], predictions: list[list[dict]], threshold: float) -> dict:
    """Greedy one-to-one matching at IoU >= 0.5 above a score threshold."""
    tp = fp = fn = 0
    for item, boxes in zip(items, predictions):
        kept = sorted((box for box in boxes if box["score"] >= threshold), key=lambda box: -box["score"])
        unmatched = list(range(len(item["boxes"])))
        for box in kept:
            best = max(unmatched, key=lambda index: iou(box["bbox"], item["boxes"][index]), default=None)
            if best is not None and iou(box["bbox"], item["boxes"][best]) >= 0.5:
                tp += 1
                unmatched.remove(best)
            else:
                fp += 1
        fn += len(unmatched)
    precision = tp / (tp + fp) if tp + fp else None
    recall = tp / (tp + fn) if tp + fn else None
    f1 = 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else None
    return {"threshold": threshold, "tp": tp, "fp": fp, "fn": fn, "precision": precision, "recall": recall, "f1": f1}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--modality", required=True)
    parser.add_argument("--anatomy", required=True)
    parser.add_argument("--category", default=None, help="COCO category name to detect (default: all).")
    parser.add_argument("--allow-flip", action="store_true", help="Horizontal flips (off for anatomy where laterality matters).")
    parser.add_argument("--epochs", type=int, default=20)
    parser.add_argument("--batch-size", type=int, default=4)
    parser.add_argument("--lr", type=float, default=0.01)
    parser.add_argument("--min-size", type=int, default=512)
    parser.add_argument("--max-size", type=int, default=1024)
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261024)
    args = parser.parse_args()

    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    dataset, task = next((d, t) for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == args.task_id)
    if not task["training_eligible"]:
        raise SystemExit(f"{args.task_id} is not training-eligible: {task['flags']}")
    prep = task["preparation"]
    rows = read_samples(Path(prep["sample_manifest"]))
    label_format = "COCO" if dataset["labels"] == "COCO" else "YOLO"
    splits = {split: load_targets([row for row in rows if row["split"] == split], label_format, args.category) for split in ("train", "val", "test")}
    set_seed(args.seed)
    dev = device()
    run = Run(args.model_id, args.task_id, {**vars(args), "dataset_version": prep["dataset_version"],
                                            "boxes_per_split": {split: sum(len(item["boxes"]) for item in items) for split, items in splits.items()}})
    model = fasterrcnn_resnet50_fpn_v2(weights=FasterRCNN_ResNet50_FPN_V2_Weights.COCO_V1, min_size=args.min_size, max_size=args.max_size)
    model.roi_heads.box_predictor = FastRCNNPredictor(model.roi_heads.box_predictor.cls_score.in_features, 2)
    model.to(dev)
    loader = DataLoader(DetectionSet(splits["train"], train=True, allow_flip=args.allow_flip), batch_size=args.batch_size, shuffle=True,
                        num_workers=args.workers, collate_fn=collate, worker_init_fn=seed_worker, generator=torch.Generator().manual_seed(args.seed),
                        persistent_workers=args.workers > 0)
    parameters = [p for p in model.parameters() if p.requires_grad]
    optimizer = torch.optim.SGD(parameters, lr=args.lr, momentum=0.9, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=args.epochs * len(loader), pct_start=0.1)
    best_state, best_ap50, best_epoch = None, -1.0, -1
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for images, targets in loader:
            images = [image.to(dev) for image in images]
            targets = [{key: value.to(dev) for key, value in target.items()} for target in targets]
            losses = model(images, targets)
            loss = sum(losses.values())
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            torch.nn.utils.clip_grad_norm_(parameters, 10.0)
            optimizer.step()
            scheduler.step()
            running += loss.item()
        val = score(splits["val"], predict(model, splits["val"], dev))
        ap50 = val["metrics"].get("ap_50") or 0.0
        run.log(epoch=epoch, train_loss=round(running / len(loader), 4), val_ap50=round(ap50, 4), val_map=round(val["metrics"].get("map_50_95") or 0.0, 4),
                gpu_peak_mib=int(torch.cuda.max_memory_allocated() / 2**20) if dev.type == "cuda" else None)
        if ap50 > best_ap50:
            best_state, best_ap50, best_epoch = copy.deepcopy({k: v.cpu() for k, v in model.state_dict().items()}), ap50, epoch
    model.load_state_dict(best_state)
    val_predictions = predict(model, splits["val"], dev)
    candidates = [operating_point(splits["val"], val_predictions, threshold) for threshold in np.round(np.arange(0.05, 0.96, 0.05), 2)]
    chosen = max(candidates, key=lambda item: item["f1"] or 0.0)

    # Test split, read once with the frozen checkpoint and the validation-chosen threshold.
    test_predictions = predict(model, splits["test"], dev)
    full = score(splits["test"], test_predictions)
    component_leakage = cross_split_component_summary(items)
    crossing_groups = component_leakage.pop("group_ids")
    clean_index = [i for i, item in enumerate(splits["test"]) if str(item.get("group_id", "")).strip() not in crossing_groups]
    clean_items = [splits["test"][i] for i in clean_index]
    filtered = score(clean_items, [test_predictions[i] for i in clean_index])
    operating = operating_point(splits["test"], test_predictions, chosen["threshold"])
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "object_detector", "arch": "fasterrcnn_resnet50_fpn_v2", "state_dict": best_state, "classes": [args.category or "target"],
        "min_size": args.min_size, "max_size": args.max_size, "score_threshold": float(chosen["threshold"]), "task_id": args.task_id,
        "dataset_version": prep["dataset_version"], "preprocessing": "RGB tensor in [0,1]; model-internal resize; boxes returned in source pixels",
    })
    predictions_path = run.write_json("predictions_test.json", [{"entry": item["entry"], "boxes": boxes} for item, boxes in zip(splits["test"], test_predictions)])
    report = {
        "model_id": args.model_id, "run_id": run.run_id, "task_id": args.task_id, "dataset": dataset["title"], "dataset_id": dataset["id"],
        "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"], "split_method": prep["split_method"], "split_counts": prep["per_split"],
        "leakage_check": {
            **{key: prep.get(key) for key in ("near_duplicate_groups_crossing_splits", "images_in_crossing_groups", "test_images_with_cross_split_duplicate", "confirmation")},
            **component_leakage,
        },
        "selection": {"criterion": "validation AP50 (COCOeval)", "best_epoch": best_epoch, "val_ap50": best_ap50},
        "operating_point": {"chosen_on": "validation", "criterion": "maximum F1 at IoU 0.5", "validation": chosen, "test": operating},
        "test": {"n_images": len(splits["test"]), "reference_boxes": sum(len(item["boxes"]) for item in splits["test"]), "metrics": full["metrics"]},
        "test_without_cross_split_duplicates": {"n_images": len(clean_items), "metrics": filtered["metrics"]},
        "evaluation_protocol": full.get("evaluation_protocol"), "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha},
        "held_out_predictions": checkpoint_ref(predictions_path), "training_seconds": run.elapsed_seconds, "config": vars(args),
        "reporting_context": {"dataset": dataset["title"], "dataset_version": prep["dataset_version"][:16], "split": "test", "checkpoint": f"sha256:{checkpoint_sha}"},
        "limitations": [
            "The registry found no identifiers in sampled metadata, but source patient IDs are unavailable; patient-level independence cannot be verified. The recorded split and near-duplicate audit are reported above.",
            "Internal test split from the same source; no external validation.",
            "Detection scores are not probabilities and are not calibrated.",
            "Research-only output; not validated for clinical use.",
        ],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    metrics = full["metrics"]
    card = [
        f"# Model card: {args.display_name}", "",
        f"- **Model id:** `{args.model_id}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Task:** {task['target']}",
        f"- **Data:** {dataset['title']} ({dataset['license']['name']}; {dataset['license']['source']}); dataset version `{prep['dataset_version'][:16]}`; {prep['split_method']}.",
        f"- **Architecture:** Faster R-CNN ResNet-50 FPN v2 (COCO-pretrained torchvision weights); best validation epoch {best_epoch}.",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.",
        "", "## Held-out test results (internal, evaluated once)", "",
        f"- COCO mAP@[.50:.95] {metrics.get('map_50_95') or 0:.3f}; AP50 {metrics.get('ap_50') or 0:.3f}; AR@100 {metrics.get('ar_100') or 0:.3f} on {len(splits['test'])} images.",
        f"- Without the {len(splits['test']) - len(clean_items)} test images that have a near-duplicate in another split: mAP {filtered['metrics'].get('map_50_95') or 0:.3f}, AP50 {filtered['metrics'].get('ap_50') or 0:.3f}.",
        f"- At the validation-chosen score threshold {chosen['threshold']}: precision {operating['precision'] or 0:.3f}, recall {operating['recall'] or 0:.3f} (IoU 0.5).",
        "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", f"Full report: `{relative(report_path)}`.",
    ]
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    (MODEL_CARDS / f"{args.model_id}.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    register_model({
        "model_id": args.model_id, "display_name": args.display_name, "domain": "medical_imaging", "task": "object_detection",
        "anatomy": args.anatomy, "framework": "torchvision fasterrcnn_resnet50_fpn_v2", "adapter": "app.services.model_inference",
        "source_repository": "medtwin/training", "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path),
        "device": "cuda_or_cpu", "supported_inputs": ["image/png", "image/jpeg"], "supported_modalities": [args.modality], "supported_classes": [args.category or "target"],
        "status": "READY_UNVALIDATED", "validated": False, "research_inference": True, "limitations": report["limitations"],
        "artifact_bundle": {
            "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"]["name"], "split_manifest_path": relative(Path(prep["sample_manifest"])),
            "task_definition": task["target"], "label_definition": {"source": label_format, "category": args.category or "all"},
            "preprocessing_version": "rgb-to-tensor-model-resize-v1", "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha,
            "calibration": None, "decision_thresholds": {"display_score_threshold": chosen["threshold"], "chosen_on": "validation max F1 at IoU 0.5"},
            "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions_path), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(MODEL_CARDS / f"{args.model_id}.md"),
        },
    })
    run.log(event="done", test_map=metrics.get("map_50_95"), test_ap50=metrics.get("ap_50"), checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
