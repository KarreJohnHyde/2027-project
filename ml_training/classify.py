"""Image classification on a prepared sample manifest (publisher class-folder labels).

Protocol (directive Sec. 7): candidate architectures are trained on the train
split only; the candidate with the best validation macro-F1 is selected;
temperature scaling is fitted on validation logits; the selected, frozen
checkpoint is evaluated once on the untouched test split. Confidence intervals
resample near-duplicate groups. Outputs are research-only and uncalibrated with
respect to any clinical population.

    python -m ml_training.classify --task-id kvasir-v2-8class --model-id gi_kvasir_v2_classifier
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
from torch import nn
from torch.utils.data import DataLoader, Dataset
from torchvision import models, transforms

from ml_training.common import (
    MODEL_CARDS,
    REPORTS,
    ROOT,
    Run,
    bootstrap_ci,
    checkpoint_ref,
    device,
    read_samples,
    register_model,
    relative,
    seed_worker,
    set_seed,
)

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import _auroc  # noqa: E402  (shared with the Validation Center)

MEAN, STD = (0.485, 0.456, 0.406), (0.229, 0.224, 0.225)
SPLITS = ("train", "val", "test")
ARCHITECTURES = {
    "resnet18": (models.resnet18, models.ResNet18_Weights.IMAGENET1K_V1),
    "efficientnet_b0": (models.efficientnet_b0, models.EfficientNet_B0_Weights.IMAGENET1K_V1),
}


class ImageSet(Dataset):
    def __init__(self, rows: list[dict], classes: list[str], transform):
        self.rows, self.index, self.transform = rows, {name: i for i, name in enumerate(classes)}, transform

    def __len__(self) -> int:
        return len(self.rows)

    def __getitem__(self, item: int):
        row = self.rows[item]
        with Image.open(row["path"]) as image:
            tensor = self.transform(image.convert("RGB"))
        return tensor, self.index[row["label"]]


def build(arch: str, classes: int) -> nn.Module:
    constructor, weights = ARCHITECTURES[arch]
    model = constructor(weights=weights)
    if arch.startswith("resnet"):
        model.fc = nn.Linear(model.fc.in_features, classes)
    else:
        model.classifier[-1] = nn.Linear(model.classifier[-1].in_features, classes)
    return model


def transforms_for(size: int):
    train = transforms.Compose([
        transforms.RandomResizedCrop(size, scale=(0.7, 1.0), ratio=(0.85, 1.18)),
        transforms.RandomHorizontalFlip(), transforms.RandomVerticalFlip(),
        transforms.ColorJitter(brightness=0.1, contrast=0.1, saturation=0.05),
        transforms.ToTensor(), transforms.Normalize(MEAN, STD),
    ])
    evaluate = transforms.Compose([transforms.Resize(int(size * 1.14)), transforms.CenterCrop(size), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    return train, evaluate


def summarize_class_distribution(rows: list[dict], classes: list[str]) -> dict:
    """Return deterministic, explicitly zero-filled class counts."""
    per_split = {
        split: {name: 0 for name in classes}
        for split in SPLITS
    }
    totals = {name: 0 for name in classes}
    for row in rows:
        label, split = row.get("label"), row.get("split")
        if label in totals:
            totals[label] += 1
            if split in per_split:
                per_split[split][label] += 1
    return {"per_split": per_split, "total": totals}


def classification_readiness(task: dict, preparation: dict, rows: list[dict], classes: list[str]) -> dict:
    """Reconcile registry readiness with the manifest actually being trained.

    Older generated registries may contain ``classes_below_minimum`` without the
    threshold or ``validation_ready`` fields. The declared rare-class list still
    fails closed for reportable validation while retaining an exploratory path.
    """
    distribution = summarize_class_distribution(rows, classes)
    minimum = preparation.get("minimum_samples_per_class", task.get("minimum_samples_per_class"))
    minimum = int(minimum) if minimum is not None else None
    declared = set(preparation.get("classes_below_minimum") or [])
    computed = {
        name for name, count in distribution["total"].items()
        if minimum is not None and count < minimum
    }
    rare_names = declared | computed
    ordered_names = [name for name in classes if name in rare_names]
    ordered_names += sorted(rare_names - set(classes))
    rare_classes = [
        {
            "class": name,
            "total": distribution["total"].get(name, 0),
            **{split: distribution["per_split"][split].get(name, 0) for split in SPLITS},
            "minimum_required": minimum,
        }
        for name in ordered_names
    ]
    source_flags = list(task.get("flags", []))
    effective_flags = list(source_flags)
    if rare_classes and "INSUFFICIENT_SAMPLES" not in effective_flags:
        effective_flags.append("INSUFFICIENT_SAMPLES")
    insufficient = "INSUFFICIENT_SAMPLES" in effective_flags
    registry_allows_validation = task.get("validation_ready") is not False
    validation_ready = bool(task.get("training_eligible")) and registry_allows_validation and not insufficient
    return {
        "validation_ready": validation_ready,
        "readiness": "READY_FOR_TRAINING" if validation_ready else "EXPLORATORY_TRAINING_ONLY",
        "run_scope": "STANDARD_INTERNAL_EVALUATION" if validation_ready else "EXPLORATORY_ONLY",
        "minimum_samples_per_class": minimum,
        "classes_below_minimum": rare_classes,
        "source_flags": source_flags,
        "effective_flags": effective_flags,
    }


def describe_rare_classes(readiness: dict) -> str:
    details = []
    for item in readiness["classes_below_minimum"]:
        details.append(
            f"{item['class']} (total={item['total']}, train={item['train']}, "
            f"val={item['val']}, test={item['test']})"
        )
    return "; ".join(details)


def require_exploratory_opt_in(readiness: dict, exploratory: bool) -> None:
    if readiness["validation_ready"] or exploratory:
        return
    rare = describe_rare_classes(readiness)
    reason = f" Rare classes: {rare}." if rare else ""
    raise SystemExit(
        "This dataset is not validation-ready and cannot be presented as a standard "
        f"evaluation run.{reason} Re-run with --exploratory to acknowledge the limitation."
    )


def class_imbalance_plan(train_rows: list[dict], classes: list[str], strategy: str) -> dict:
    """Build a deterministic loss-weighting plan from training data only.

    The balanced inverse-frequency formula is ``N / (K * n_c)``. This makes the
    aggregate contribution of each observed class equal without consulting the
    validation or test labels for optimisation.
    """
    if strategy not in {"none", "inverse_frequency"}:
        raise ValueError(f"Unsupported class-weighting strategy: {strategy}")
    if not classes:
        raise ValueError("Classification requires at least one output class.")
    counts = {name: 0 for name in classes}
    for row in train_rows:
        if row.get("label") in counts:
            counts[row["label"]] += 1
    missing = [name for name, count in counts.items() if count == 0]
    if missing:
        raise ValueError(
            "Every output class requires at least one training sample; "
            f"missing: {', '.join(missing)}"
        )

    weights = None
    formula = None
    if strategy == "inverse_frequency":
        sample_count, class_count = sum(counts.values()), len(classes)
        weights = {
            name: sample_count / (class_count * counts[name])
            for name in classes
        }
        formula = "w_c = N_train / (K * n_train,c)"
    return {
        "strategy": strategy,
        "enabled": strategy != "none",
        "formula": formula,
        "computed_from": "training split only",
        "training_counts": counts,
        "weights_by_class": weights,
        "normalization": "equal aggregate training-loss contribution per observed class" if weights else None,
    }


def class_weight_tensor(plan: dict, classes: list[str], dev: torch.device) -> torch.Tensor | None:
    weights = plan["weights_by_class"]
    if weights is None:
        return None
    return torch.tensor([weights[name] for name in classes], dtype=torch.float32, device=dev)


def classification_limitations(readiness: dict, imbalance: dict, group_unit: str = "near-duplicate group") -> list[str]:
    if group_unit == "subject cluster":
        separation = ("Subject ids come from the publisher's file names. Identical images occur under different subject ids, so subjects sharing an image "
                      "were joined into clusters, training subjects linked to the test set were removed, and the bootstrap resamples clusters; whether "
                      "an id denotes one patient cannot be verified.")
    else:
        separation = ("The registry found no identifiers in sampled metadata, but the source provides no patient IDs; patient-level separation cannot "
                      "be verified. Splits keep confirmed near-duplicate groups together.")
    limitations = [
        separation,
        "Internal held-out test from the same source distribution; no external validation.",
        "Temperature scaling was fitted on the internal validation split; probabilities are not calibrated for any clinical population.",
        "Research-only output; not validated for clinical use.",
    ]
    if readiness["classes_below_minimum"]:
        threshold = readiness["minimum_samples_per_class"]
        threshold_text = f"the declared minimum of {threshold}" if threshold is not None else "the audit's declared minimum"
        limitations.insert(
            0,
            f"INSUFFICIENT_SAMPLES: classes below {threshold_text}: {describe_rare_classes(readiness)}. "
            "This run was explicitly exploratory; rare-class estimates are unstable and are not validation-ready.",
        )
    elif not readiness["validation_ready"]:
        limitations.insert(
            0,
            "The dataset registry marks this task as not validation-ready. This run was explicitly exploratory and its metrics are not eligible for validation claims.",
        )
    if imbalance["enabled"]:
        limitations.insert(
            1 if not readiness["validation_ready"] else 0,
            "Training used inverse-frequency weighted cross-entropy computed from the training split only. Weighting changes optimisation but does not create rare-class evidence or correct evaluation uncertainty.",
        )
    return limitations


@torch.no_grad()
def logits_for(model: nn.Module, loader: DataLoader, dev: torch.device) -> tuple[np.ndarray, np.ndarray]:
    model.eval()
    outputs, targets = [], []
    for images, labels in loader:
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            outputs.append(model(images.to(dev, non_blocking=True)).float().cpu())
        targets.append(labels)
    return torch.cat(outputs).numpy(), torch.cat(targets).numpy()


def macro_f1(y: np.ndarray, pred: np.ndarray, classes: int) -> float:
    scores = []
    for k in range(classes):
        tp = np.sum((pred == k) & (y == k))
        fp = np.sum((pred == k) & (y != k))
        fn = np.sum((pred != k) & (y == k))
        scores.append(0.0 if 2 * tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn))
    return float(np.mean(scores))


def balanced_accuracy(y: np.ndarray, pred: np.ndarray, classes: int) -> float:
    recalls = [np.mean(pred[y == k] == k) for k in range(classes) if np.any(y == k)]
    return float(np.mean(recalls))


def softmax(logits: np.ndarray, temperature: float = 1.0) -> np.ndarray:
    scaled = logits / temperature
    scaled -= scaled.max(axis=1, keepdims=True)
    exp = np.exp(scaled)
    return exp / exp.sum(axis=1, keepdims=True)


def fit_temperature(logits: np.ndarray, targets: np.ndarray) -> float:
    """Temperature scaling (Guo et al., 2017) by NLL minimisation on validation logits."""
    log_t = torch.zeros(1, requires_grad=True)
    tensor, labels = torch.from_numpy(logits).float(), torch.from_numpy(targets).long()
    optimizer = torch.optim.LBFGS([log_t], lr=0.1, max_iter=200)

    def closure():
        optimizer.zero_grad()
        loss = nn.functional.cross_entropy(tensor / log_t.exp(), labels)
        loss.backward()
        return loss

    optimizer.step(closure)
    return float(log_t.exp().item())


def expected_calibration_error(probabilities: np.ndarray, targets: np.ndarray, bins: int = 15) -> float:
    confidence = probabilities.max(axis=1)
    correct = probabilities.argmax(axis=1) == targets
    edges = np.linspace(0, 1, bins + 1)
    ece = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (confidence > low) & (confidence <= high)
        if mask.any():
            ece += mask.mean() * abs(correct[mask].mean() - confidence[mask].mean())
    return float(ece)


def train_candidate(
    arch: str,
    loaders: dict,
    classes: int,
    args,
    dev: torch.device,
    run: Run,
    loss_weights: torch.Tensor | None,
) -> tuple[dict, float, int]:
    model = build(arch, classes).to(dev)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, total_steps=args.epochs * len(loaders["train"]), pct_start=0.15)
    criterion = nn.CrossEntropyLoss(weight=loss_weights)
    best_state, best_f1, best_epoch = None, -1.0, -1
    for epoch in range(1, args.epochs + 1):
        model.train()
        running, seen = 0.0, 0
        for images, labels in loaders["train"]:
            images, labels = images.to(dev, non_blocking=True), labels.to(dev, non_blocking=True)
            optimizer.zero_grad(set_to_none=True)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                loss = criterion(model(images), labels)
            loss.backward()
            optimizer.step()
            scheduler.step()
            running += loss.item() * len(labels)
            seen += len(labels)
        val_logits, val_targets = logits_for(model, loaders["val"], dev)
        f1 = macro_f1(val_targets, val_logits.argmax(1), classes)
        run.log(arch=arch, epoch=epoch, train_loss=round(running / seen, 4), val_macro_f1=round(f1, 4),
                gpu_peak_mib=int(torch.cuda.max_memory_allocated() / 2**20) if dev.type == "cuda" else None)
        if f1 > best_f1:
            best_state, best_f1, best_epoch = copy.deepcopy({k: v.cpu() for k, v in model.state_dict().items()}), f1, epoch
    return best_state, best_f1, best_epoch


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--task-id", required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--display-name", required=True)
    parser.add_argument("--modality", required=True)
    parser.add_argument("--anatomy", required=True)
    parser.add_argument("--archs", default="resnet18,efficientnet_b0")
    parser.add_argument("--epochs", type=int, default=8)
    parser.add_argument("--batch-size", type=int, default=48)
    parser.add_argument("--image-size", type=int, default=224)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-4)
    parser.add_argument(
        "--class-weighting",
        choices=("inverse_frequency", "none"),
        default="inverse_frequency",
        help="Training-loss weighting. Inverse frequency uses N_train / (K * n_train,c).",
    )
    parser.add_argument(
        "--exploratory",
        action="store_true",
        help="Explicitly permit training when the audited dataset is not validation-ready.",
    )
    parser.add_argument("--workers", type=int, default=4)
    parser.add_argument("--seed", type=int, default=20261024)
    args = parser.parse_args()

    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    dataset, task = next((d, t) for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == args.task_id)
    if not task["training_eligible"]:
        raise SystemExit(f"{args.task_id} is not training-eligible: {task['flags']}")
    prep = task["preparation"]
    rows = read_samples(Path(prep["sample_manifest"]))
    classes = sorted({row["label"] for row in rows})
    splits = {split: [row for row in rows if row["split"] == split] for split in SPLITS}
    distribution = summarize_class_distribution(rows, classes)
    readiness = classification_readiness(task, prep, rows, classes)
    require_exploratory_opt_in(readiness, args.exploratory)
    try:
        imbalance = class_imbalance_plan(splits["train"], classes, args.class_weighting)
    except ValueError as exc:
        raise SystemExit(str(exc)) from exc
    set_seed(args.seed)
    dev = device()
    run = Run(
        args.model_id,
        args.task_id,
        {
            **vars(args),
            "classes": classes,
            "dataset_version": prep["dataset_version"],
            "validation_readiness": readiness,
            "class_distribution": distribution,
            "class_imbalance": imbalance,
        },
    )
    train_tf, eval_tf = transforms_for(args.image_size)
    loss_weights = class_weight_tensor(imbalance, classes, dev)
    generator = torch.Generator().manual_seed(args.seed)
    loaders = {
        "train": DataLoader(ImageSet(splits["train"], classes, train_tf), batch_size=args.batch_size, shuffle=True, num_workers=args.workers,
                            pin_memory=True, worker_init_fn=seed_worker, generator=generator, persistent_workers=args.workers > 0, drop_last=True),
        "val": DataLoader(ImageSet(splits["val"], classes, eval_tf), batch_size=args.batch_size * 2, num_workers=args.workers, pin_memory=True, persistent_workers=args.workers > 0),
    }
    candidates = {}
    for arch in args.archs.split(","):
        state, f1, epoch = train_candidate(arch, loaders, len(classes), args, dev, run, loss_weights)
        candidates[arch] = {"state": state, "val_macro_f1": f1, "best_epoch": epoch}
    selected = max(candidates, key=lambda arch: candidates[arch]["val_macro_f1"])
    model = build(selected, len(classes)).to(dev)
    model.load_state_dict(candidates[selected]["state"])
    val_logits, val_targets = logits_for(model, loaders["val"], dev)
    temperature = fit_temperature(val_logits, val_targets)

    # The test split is read exactly once, with the frozen selected checkpoint.
    test_loader = DataLoader(ImageSet(splits["test"], classes, eval_tf), batch_size=args.batch_size * 2, num_workers=args.workers, pin_memory=True)
    logits, y = logits_for(model, test_loader, dev)
    raw, calibrated = softmax(logits), softmax(logits, temperature)
    pred = calibrated.argmax(1)
    groups = np.array([row["group_id"] for row in splits["test"]])
    k = len(classes)
    confusion = np.zeros((k, k), dtype=int)
    for true, guess in zip(y, pred):
        confusion[true, guess] += 1
    per_class = []
    for index, name in enumerate(classes):
        tp, fp, fn = confusion[index, index], confusion[:, index].sum() - confusion[index, index], confusion[index, :].sum() - confusion[index, index]
        per_class.append({"class": name, "support": int(confusion[index].sum()), "precision": float(tp / (tp + fp)) if tp + fp else None,
                          "recall": float(tp / (tp + fn)) if tp + fn else None, "f1": float(2 * tp / (2 * tp + fp + fn)) if 2 * tp + fp + fn else None,
                          "auroc_one_vs_rest": _auroc((y == index).astype(int), calibrated[:, index])})
    accuracy = float(np.mean(pred == y))
    metrics = {
        "accuracy": accuracy, "balanced_accuracy": balanced_accuracy(y, pred, k), "macro_f1": macro_f1(y, pred, k),
        "macro_auroc_one_vs_rest": float(np.mean([item["auroc_one_vs_rest"] for item in per_class if item["auroc_one_vs_rest"] is not None])),
        "ece_uncalibrated": expected_calibration_error(raw, y), "ece_temperature_scaled": expected_calibration_error(calibrated, y),
        "brier_multiclass": float(np.mean(np.sum((calibrated - np.eye(k)[y]) ** 2, axis=1))),
    }
    intervals = {
        "accuracy": bootstrap_ci(lambda idx: float(np.mean(pred[idx] == y[idx])), len(y), groups),
        "macro_f1": bootstrap_ci(lambda idx: macro_f1(y[idx], pred[idx], k), len(y), groups),
        "balanced_accuracy": bootstrap_ci(lambda idx: balanced_accuracy(y[idx], pred[idx], k), len(y), groups),
    }
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "image_classifier", "arch": selected, "state_dict": candidates[selected]["state"], "classes": classes,
        "image_size": args.image_size, "normalization": {"mean": MEAN, "std": STD}, "temperature": temperature,
        "task_id": args.task_id, "dataset_version": prep["dataset_version"], "preprocessing": "RGB; resize to 1.14x then centre-crop; ImageNet normalisation",
        "validation_readiness": readiness, "class_imbalance": imbalance,
    })
    predictions = run.directory / "predictions_test.csv"
    with predictions.open("w", encoding="utf-8") as handle:
        handle.write("entry,group_id,y_true,y_pred,confidence," + ",".join(f"p_{name}" for name in classes) + "\n")
        for row, true, guess, probs in zip(splits["test"], y, pred, calibrated):
            handle.write(f"\"{row['entry']}\",{row['group_id']},{classes[true]},{classes[guess]},{probs.max():.6f}," + ",".join(f"{p:.6f}" for p in probs) + "\n")
    failures = sorted(([row["entry"], classes[true], classes[guess], float(probs.max())] for row, true, guess, probs in zip(splits["test"], y, pred, calibrated) if true != guess),
                      key=lambda item: -item[3])[:25]
    group_unit = prep.get("group_unit", "near-duplicate group")
    limitations = classification_limitations(readiness, imbalance, group_unit)
    report = {
        "model_id": args.model_id, "run_id": run.run_id, "task_id": args.task_id, "dataset": dataset["title"], "dataset_id": dataset["id"],
        "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"], "split_method": prep["split_method"],
        "split_counts": prep["per_split"], "test_n": int(len(y)), "test_groups": int(len(np.unique(groups))), "group_unit": group_unit, "classes": classes,
        "validation_readiness": readiness, "run_scope": readiness["run_scope"],
        "class_distribution": distribution, "class_imbalance": imbalance,
        "selection": {"criterion": "validation macro-F1", "candidates": {a: {"val_macro_f1": c["val_macro_f1"], "best_epoch": c["best_epoch"]} for a, c in candidates.items()}, "selected": selected},
        "calibration": {"method": "temperature_scaling", "fitted_on": "validation split", "temperature": temperature},
        "metrics": metrics, "confidence_intervals_95": intervals, "per_class": per_class, "confusion_matrix": confusion.tolist(),
        "highest_confidence_errors": failures, "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha},
        "held_out_predictions": checkpoint_ref(predictions), "training_seconds": run.elapsed_seconds, "config": {k2: v for k2, v in vars(args).items()},
        "reporting_context": {
            "dataset": dataset["title"], "dataset_version": prep["dataset_version"][:16], "split": "test",
            "checkpoint": f"sha256:{checkpoint_sha}",
            "reporting_status": "INTERNAL_HELD_OUT" if readiness["validation_ready"] else "EXPLORATORY",
        },
        "limitations": limitations,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    write_model_card(args, dataset, report, report_path)
    register_model({
        "model_id": args.model_id, "display_name": args.display_name, "domain": "medical_imaging", "task": "image_classification",
        "anatomy": args.anatomy, "framework": f"torchvision {selected}", "adapter": "app.services.model_inference",
        "source_repository": "medtwin/training", "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path),
        "device": "cuda_or_cpu", "supported_inputs": ["image/jpeg", "image/png"], "supported_modalities": [args.modality], "supported_classes": classes,
        "status": "READY_UNVALIDATED", "validated": False, "research_inference": True,
        "validation_readiness": readiness, "class_distribution": distribution, "class_imbalance": imbalance,
        "limitations": report["limitations"],
        "artifact_bundle": {
            "dataset_version": prep["dataset_version"], "dataset_license": dataset["license"]["name"],
            "split_manifest_path": relative(Path(prep["sample_manifest"])), "task_definition": task["target"],
            "label_definition": {"source": "publisher class folders", "classes": classes},
            "preprocessing_version": "rgb-resize114-centercrop-imagenetnorm-v1", "checkpoint_path": checkpoint_ref(checkpoint_path),
            "checkpoint_sha256": checkpoint_sha, "calibration": {"method": "temperature_scaling", "parameters": {"temperature": temperature}},
            "decision_thresholds": {"rule": "argmax over temperature-scaled softmax"}, "abstention_thresholds": None,
            "validation_readiness": readiness, "class_distribution": distribution, "class_imbalance": imbalance,
            "held_out_predictions_path": checkpoint_ref(predictions), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(MODEL_CARDS / f"{args.model_id}.md"),
        },
    })
    run.log(event="done", selected=selected, test_accuracy=round(accuracy, 4), test_macro_f1=round(metrics["macro_f1"], 4), checkpoint_sha256=checkpoint_sha)
    return 0


def write_model_card(args, dataset: dict, report: dict, report_path: Path) -> None:
    metrics, intervals = report["metrics"], report["confidence_intervals_95"]
    readiness, imbalance = report["validation_readiness"], report["class_imbalance"]

    def ci(name: str) -> str:
        interval = intervals[name]
        return f"{interval['low']:.3f}-{interval['high']:.3f}" if interval.get("status") == "COMPUTED" else "not computed"

    weighting = "unweighted cross-entropy"
    if imbalance["enabled"]:
        weighting = f"inverse-frequency weighted cross-entropy (`{imbalance['formula']}`), computed from training counts only"
    adequacy = [
        f"- **Run scope:** `{report['run_scope']}`; validation-ready: `{str(readiness['validation_ready']).lower()}`.",
        f"- **Training loss:** {weighting}.",
    ]
    if readiness["classes_below_minimum"]:
        threshold = readiness["minimum_samples_per_class"]
        minimum = str(threshold) if threshold is not None else "recorded by the source audit (threshold unavailable in this registry version)"
        adequacy.append(f"- **Minimum samples per class:** {minimum}.")
        adequacy.extend(
            f"- **Rare class:** {item['class']} — total {item['total']} (train {item['train']}, validation {item['val']}, test {item['test']})."
            for item in readiness["classes_below_minimum"]
        )
    else:
        adequacy.append("- The source audit did not flag any class for insufficient samples.")

    lines = [
        f"# Model card: {args.display_name}", "",
        f"- **Model id:** `{args.model_id}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Task:** {report['task_id']} — {', '.join(report['classes'])}",
        f"- **Data:** {dataset['title']} ({dataset['license']['name']}; source {dataset['license']['source']}). Dataset version `{report['dataset_version'][:16]}`.",
        f"- **Split:** {report['split_method']}; counts {report['split_counts']}.",
        f"- **Architecture:** {report['selection']['selected']} (selected by validation macro-F1 from {', '.join(report['selection']['candidates'])}), ImageNet-pretrained torchvision weights.",
        f"- **Checkpoint:** `{report['checkpoint']['path']}`, SHA-256 `{report['checkpoint']['sha256']}`.",
        "", "## Data adequacy and class imbalance", "",
        *adequacy,
        "", "## Held-out test results (internal, evaluated once)", "",
        f"- Accuracy {metrics['accuracy']:.3f} (95% CI {ci('accuracy')}); macro-F1 {metrics['macro_f1']:.3f} (95% CI {ci('macro_f1')}); balanced accuracy {metrics['balanced_accuracy']:.3f} (95% CI {ci('balanced_accuracy')}).",
        f"- Macro one-vs-rest AUROC {metrics['macro_auroc_one_vs_rest']:.3f}. ECE {metrics['ece_uncalibrated']:.3f} uncalibrated, {metrics['ece_temperature_scaled']:.3f} after temperature scaling (T = {report['calibration']['temperature']:.3f}).",
        f"- n = {report['test_n']} test images in {report['test_groups']} {report.get('group_unit', 'near-duplicate group')}s (bootstrap unit).",
        "", "## Limitations", "",
        *[f"- {item}" for item in report["limitations"]],
        "", f"Full report: `{relative(report_path)}`.",
    ]
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    (MODEL_CARDS / f"{args.model_id}.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    sys.exit(main())
