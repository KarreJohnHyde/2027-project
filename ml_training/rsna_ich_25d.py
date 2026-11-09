"""Intracranial haemorrhage on head CT with neighbouring slices (2.5-D): RSNA ICH, multi-label.

Same data, licence, patient split (seed), backbone, transforms and schedule as ml_training/rsna_ich.py; only the
input differs. Each sample stacks three single-window PNG slices of one series as the three image channels: the slice
below, the slice and the slice above, ordered by ImagePositionPatient z within the series (train_metadata.csv).
At the ends of a series the slice itself stands in for the missing neighbour. Labels are those of the middle slice.

Evaluation reads the held-out test patients once and compares the model with the single-slice model on the same test
slices (paired bootstrap over patients). Serving takes an ordered DICOM series converted with the window the PNGs
were exported with (rsna_ich.DICOM_WINDOW; docs/validation/RSNA_PNG_WINDOW_ESTIMATE.md). Research use only.

    python -m ml_training.rsna_ich_25d --epochs 3 --resume-file artifacts/training/resume/rsna_25d.pt
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader
from torchvision import transforms

from ml_training import rsna_ich as single
from ml_training.common import (MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, device, load_resume, register_model, relative,
                                save_resume, seed_worker, set_seed)

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import _auroc  # noqa: E402

MODEL_ID = "brain_ct_rsna_ich_25d_classifier"
TASK_ID = single.TASK_ID
LABELS, NAMES, MEAN, STD = single.LABELS, single.NAMES, single.MEAN, single.STD
BASE = ROOT / "_derived" / "datasets" / "rsna-ich-25d"
MANIFEST = BASE / "samples.csv"
OOD_COUNTS = {"train": 3000, "val": 1500, "test": 1500}
CONTEXT = {"neighbours_each_side": 1, "channel_order": ["slice below", "slice", "slice above"],
           "ordering": "ImagePositionPatient z within the series (projection on the slice normal at serving time)",
           "series_ends": "the slice itself replaces a missing neighbour"}


def series_positions() -> dict[str, tuple[str, float]]:
    """SOPInstanceUID -> (series, z) from the archive's metadata."""
    with zipfile.ZipFile(single.ARCHIVE) as archive, archive.open("train_metadata.csv") as handle:
        return {row["SOPInstanceUID"]: (row["SeriesInstanceUID"], float(row["ImagePositionPatient_2"]))
                for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))}


def sop_of(entry: str) -> str:
    return entry.rsplit("-", 1)[-1][:-4]


def neighbours(rows: list[dict], positions: dict[str, tuple[str, float]]) -> tuple[np.ndarray, np.ndarray]:
    """For each row, the indices (into ``rows``) of the slices below and above it in its series."""
    by_series: dict[str, list[tuple[float, int]]] = {}
    for index, row in enumerate(rows):
        series, z = positions[sop_of(row["entry"])]
        by_series.setdefault(series, []).append((z, index))
    below, above = np.arange(len(rows)), np.arange(len(rows))
    for items in by_series.values():
        ordered = [index for _, index in sorted(items)]
        for position, index in enumerate(ordered):
            below[index] = ordered[max(0, position - 1)]
            above[index] = ordered[min(len(ordered) - 1, position + 1)]
    return below, above


def stack(slices: list[Image.Image]) -> Image.Image:
    return Image.merge("RGB", [image.convert("L") for image in slices])


class StackSet(single.SliceSet):
    """Three slices of one series per sample, read from the archive by byte offset."""

    def __init__(self, rows: list[dict], transform, positions: dict[str, tuple[str, float]]):
        super().__init__(rows, transform)
        self.below, self.above = neighbours(rows, positions)

    def image(self, index: int) -> Image.Image:
        return stack([Image.open(io.BytesIO(self._member(int(j)))) for j in (self.below[index], index, self.above[index])])

    def __getitem__(self, index: int):
        return self.transform(self.image(index)), torch.from_numpy(self.targets[index])


def paired_comparison(rows: list[dict], y: np.ndarray, p: np.ndarray, single_predictions: Path) -> dict:
    """This model minus the single-slice model on the same test slices: mean AUROC and study-level 'any' AUROC."""
    if not single_predictions.exists():
        return {"status": "NOT_COMPUTED_SINGLE_SLICE_PREDICTIONS_MISSING"}
    with single_predictions.open(encoding="utf-8") as handle:
        other = {row["entry"]: [float(row[f"p_{key}"]) for key in LABELS] for row in csv.DictReader(handle)}
    if any(row["entry"] not in other for row in rows):
        return {"status": "NOT_COMPUTED_TEST_SLICES_DIFFER"}
    q = np.array([other[row["entry"]] for row in rows])
    patients = np.array([row["patient"] for row in rows])

    def mean_auroc(probabilities, index):
        values = [_auroc(y[index, i], probabilities[index, i]) for i in range(len(LABELS))]
        values = [value for value in values if value is not None]
        return float(np.mean(values)) if values else None

    def difference(index):
        a, b = mean_auroc(p, index), mean_auroc(q, index)
        return None if a is None or b is None else a - b

    everything = np.arange(len(rows))
    return {"status": "COMPUTED", "unit": "test slice, resampled by patient", "single_slice_mean_auroc": mean_auroc(q, everything),
            "this_model_mean_auroc": mean_auroc(p, everything), "difference": difference(everything),
            "difference_ci95": bootstrap_ci(difference, len(rows), patients, rounds=300, unit="patient")}


def export_ood_sample(rows: list[dict], positions: dict[str, tuple[str, float]], seed: int) -> Path:
    """Stacked inputs for the applicability reference (scripts/build_image_ood_references.py reads image files)."""
    out = []
    by_split = {split: [row for row in rows if row["split"] == split] for split in OOD_COUNTS}
    for split, count in OOD_COUNTS.items():
        items = by_split[split]
        dataset = StackSet(items, None, positions)
        chosen = sorted(random.Random(f"{seed}:{split}").sample(range(len(items)), min(count, len(items))))
        for index in chosen:
            target = BASE / "ood_sample" / split / f"{sop_of(items[index]['entry'])}.png"
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                dataset.image(index).save(target)
            out.append({"entry": items[index]["entry"], "path": target.relative_to(ROOT).as_posix(), "split": split})
    path = BASE / "ood_sample.csv"
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["entry", "path", "split"])
        writer.writeheader()
        writer.writerows(out)
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20261104)  # the single-slice model's seed: the same patient split
    parser.add_argument("--max-train-slices", type=int, default=0, help="0 = every training slice")
    parser.add_argument("--resume-file", type=Path, default=None)
    parser.add_argument("--smoke-series", type=int, default=0,
                        help="Pipeline check: this many series per split; nothing is registered or written outside the run directory.")
    args = parser.parse_args()
    set_seed(args.seed)
    rows = single.read_samples(args.seed)
    positions = series_positions()
    BASE.mkdir(parents=True, exist_ok=True)
    version = single.write_manifest(rows)  # the same sample manifest and version as the single-slice model
    if args.smoke_series:
        kept = {split: sorted({positions[sop_of(row["entry"])][0] for row in rows if row["split"] == split})[: args.smoke_series]
                for split in ("train", "val", "test")}
        rows = [row for row in rows if positions[sop_of(row["entry"])][0] in kept[row["split"]]]
    splits = {name: [row for row in rows if row["split"] == name] for name in ("train", "val", "test")}
    train_rows = splits["train"]
    if args.max_train_slices and len(train_rows) > args.max_train_slices:
        # A subsample keeps whole series, so every slice still has its real neighbours.
        series = sorted({positions[sop_of(row["entry"])][0] for row in train_rows})
        random.Random(args.seed).shuffle(series)
        keep, total = set(), 0
        per_series: dict[str, int] = {}
        for row in train_rows:
            key = positions[sop_of(row["entry"])][0]
            per_series[key] = per_series.get(key, 0) + 1
        for key in series:
            if total >= args.max_train_slices:
                break
            keep.add(key)
            total += per_series[key]
        train_rows = [row for row in train_rows if positions[sop_of(row["entry"])][0] in keep]
    run = Run(MODEL_ID, TASK_ID, {**vars(args), "resume_file": str(args.resume_file), "dataset_version": version, "context": CONTEXT,
                                  "split_counts": {k: len(v) for k, v in splits.items()}})
    dev = device()
    train_tf = transforms.Compose([transforms.RandomResizedCrop(args.image_size, scale=(0.85, 1.0), ratio=(0.95, 1.05)),
                                   transforms.RandomHorizontalFlip(), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    eval_tf = transforms.Compose([transforms.Resize(args.image_size), transforms.CenterCrop(args.image_size), transforms.ToTensor(),
                                  transforms.Normalize(MEAN, STD)])
    # The resume state is bound to the exact training and validation populations, not only to the settings.
    population = hashlib.sha256("\n".join(sorted(f"{row['split']}:{row['entry']}" for row in [*train_rows, *splits["val"]])).encode("utf-8")).hexdigest()
    identity = {key: getattr(args, key) for key in ("epochs", "batch_size", "image_size", "lr", "seed", "max_train_slices", "smoke_series")} | {
        "dataset_version": version, "population_sha256": population}
    resumed = load_resume(args.resume_file, identity)
    start_epoch = 1 if resumed is None else int(resumed["epoch"]) + 1
    loader_args = {"num_workers": args.workers, "pin_memory": True, "worker_init_fn": seed_worker}
    train_loader = DataLoader(StackSet(train_rows, train_tf, positions), batch_size=args.batch_size, shuffle=True, drop_last=True,
                              generator=torch.Generator().manual_seed(args.seed + start_epoch - 1), persistent_workers=args.workers > 0, **loader_args)
    val_set = StackSet(splits["val"], eval_tf, positions)
    val_loader = DataLoader(val_set, batch_size=args.batch_size * 2, **loader_args)
    model = single.build_model().to(dev)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=max(1, args.epochs * len(train_loader)))
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    loss_fn = nn.BCEWithLogitsLoss()
    best = {"score": -1.0}
    if resumed is not None:
        model.load_state_dict(resumed["model"])
        optimiser.load_state_dict(resumed["optimizer"])
        scheduler.load_state_dict(resumed["scheduler"])
        scaler.load_state_dict(resumed["scaler"])
        best = resumed["best"]
        run.log(resumed_from_epoch=int(resumed["epoch"]), resume_file=str(args.resume_file))
    for epoch in range(start_epoch, args.epochs + 1):
        model.train()
        total, seen = 0.0, 0
        for step, (images, targets) in enumerate(train_loader, start=1):
            images, targets = images.to(dev, non_blocking=True), targets.to(dev, non_blocking=True)
            optimiser.zero_grad(set_to_none=True)
            with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
                loss = loss_fn(model(images), targets)
            scaler.scale(loss).backward()
            scaler.step(optimiser)
            scaler.update()
            scheduler.step()
            total, seen = total + float(loss) * len(images), seen + len(images)
            if step % 500 == 0:
                run.log(epoch=epoch, step=step, of=len(train_loader), train_loss=round(total / seen, 4))
        probabilities = single.predict(model, val_loader, dev)
        aurocs = {key: _auroc(val_set.targets[:, i].astype(int), probabilities[:, i]) for i, key in enumerate(LABELS)}
        defined = [value for value in aurocs.values() if value is not None]
        score = float(np.mean(defined)) if defined else 0.0
        run.log(epoch=epoch, train_loss=round(total / max(1, seen), 4), val_mean_auroc=round(score, 4),
                val_auroc={k: None if v is None else round(v, 4) for k, v in aurocs.items()})
        if score > best["score"]:
            best = {"score": score, "epoch": epoch, "state": {k: v.detach().cpu().clone() for k, v in model.state_dict().items()},
                    "val_probabilities": probabilities}
        save_resume(args.resume_file, identity, {"epoch": epoch, "model": model.state_dict(), "optimizer": optimiser.state_dict(),
                                                 "scheduler": scheduler.state_dict(), "scaler": scaler.state_dict(), "best": best})
    model.load_state_dict(best["state"])
    thresholds = {key: single.youden_threshold(val_set.targets[:, i], best["val_probabilities"][:, i]) for i, key in enumerate(LABELS)}

    # The test patients are read exactly once, with the frozen selected checkpoint.
    test_set = StackSet(splits["test"], eval_tf, positions)
    p = single.predict(model, DataLoader(test_set, batch_size=args.batch_size * 2, **loader_args), dev)
    y = test_set.targets.astype(int)
    patients = np.array([row["patient"] for row in splits["test"]])
    per_label = {}
    for i, key in enumerate(LABELS):
        guess = (p[:, i] >= thresholds[key]).astype(int)
        per_label[key] = {"name": NAMES[key], "positives": int(y[:, i].sum()), "auroc": _auroc(y[:, i], p[:, i]),
                          "auroc_ci95": bootstrap_ci(lambda idx, i=i: _auroc(y[idx, i], p[idx, i]), len(y), patients, rounds=300, unit="patient"),
                          "threshold_from_validation": round(thresholds[key], 6),
                          "sensitivity": float(guess[y[:, i] == 1].mean()) if y[:, i].any() else None,
                          "specificity": float(1 - guess[y[:, i] == 0].mean()) if (1 - y[:, i]).any() else None}
    studies: dict[str, list[int]] = {}
    for index, row in enumerate(splits["test"]):
        studies.setdefault(row["study"], []).append(index)
    keys = sorted(studies)
    any_index = LABELS.index("any")
    study_truth = np.array([int(y[studies[key], any_index].max()) for key in keys])
    study_score = np.array([float(p[studies[key], any_index].max()) for key in keys])
    study_patients = np.array([splits["test"][studies[key][0]]["patient"] for key in keys])
    study_level = {"unit": "study (highest slice probability of 'any')", "studies": len(keys), "positive_studies": int(study_truth.sum()),
                   "auroc": _auroc(study_truth, study_score),
                   "auroc_ci95": bootstrap_ci(lambda idx: _auroc(study_truth[idx], study_score[idx]), len(keys), study_patients, rounds=500, unit="patient")}
    single_report = json.loads((REPORTS / f"{single.MODEL_ID}.json").read_text(encoding="utf-8"))
    comparison = paired_comparison(splits["test"], y, p, ROOT / single_report["held_out_predictions"])
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "image_multilabel_classifier", "arch": "efficientnet_b0", "state_dict": best["state"], "classes": [NAMES[key] for key in LABELS],
        "label_keys": list(LABELS), "image_size": args.image_size, "normalization": {"mean": MEAN, "std": STD}, "thresholds": thresholds,
        "task_id": TASK_ID, "dataset_version": version, "context": CONTEXT,
        "preprocessing": "three single-window greyscale slices (below, slice, above) as the RGB channels; short side to 256 px, centre 256 x 256 "
                         "crop; ImageNet normalisation",
    })
    predictions = run.directory / "predictions_test.csv"
    with predictions.open("w", encoding="utf-8") as handle:
        handle.write("entry,patient,study," + ",".join(f"y_{k}" for k in LABELS) + "," + ",".join(f"p_{k}" for k in LABELS) + "\n")
        for row, truth, probs in zip(splits["test"], y, p):
            handle.write(f"{row['entry']},{row['patient']},{row['study']}," + ",".join(map(str, truth)) + "," + ",".join(f"{v:.6f}" for v in probs) + "\n")
    if args.smoke_series:
        run.write_json("smoke.json", {"test_slices": int(len(y)), "per_label_auroc": {key: item["auroc"] for key, item in per_label.items()},
                                      "comparison_status": comparison["status"], "neighbour_example": [int(test_set.below[5]), 5, int(test_set.above[5])]})
        print(json.dumps({"smoke": True, "run": run.run_id, "test_slices": int(len(y))}), flush=True)
        return 0
    ood_manifest = export_ood_sample(rows, positions, args.seed)
    limitations = [
        "Haemorrhage subtypes only (RSNA labels); no ischaemic stroke, tumour, infection or other pathology.",
        "Sees one slice above and below; slice spacing and gantry tilt vary within the RSNA collection and are not normalised.",
        "Serving needs an ordered DICOM series converted with the export window measured from the training PNGs (width measured, level "
        "estimated: docs/validation/RSNA_PNG_WINDOW_ESTIMATE.md); real DICOM series have not been evaluated here.",
        "Internal held-out test on unseen patients of the same RSNA collection; no external validation.",
        "Operating thresholds come from the validation patients (Youden's J); probabilities are not calibrated for any clinical population.",
        "Research-only output; not validated for clinical use.",
    ]
    report = {
        "model_id": MODEL_ID, "run_id": run.run_id, "task_id": TASK_ID, "dataset": "RSNA Intracranial Hemorrhage Detection (PNG conversion)",
        "dataset_version": version, "dataset_license": single.LICENSE, "split_method": f"whole patients 80/10/10, seed {args.seed} (as the single-slice model)",
        "context": CONTEXT, "split_counts": {name: len(items) for name, items in splits.items()}, "train_slices_used": len(train_rows),
        "patients_per_split": {name: len({row["patient"] for row in items}) for name, items in splits.items()},
        "selection": {"criterion": "mean validation AUROC over the six labels", "best_epoch": best["epoch"], "val_mean_auroc": best["score"],
                      "resumed_from_epoch": None if resumed is None else int(resumed["epoch"])},
        "test_n": int(len(y)), "test_patients": int(len(np.unique(patients))), "group_unit": "patient",
        "per_label": per_label, "mean_auroc": float(np.mean([item["auroc"] for item in per_label.values()])), "study_level_any": study_level,
        "paired_comparison_with_single_slice_model": comparison,
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions),
        "training_seconds": run.elapsed_seconds, "config": {**vars(args), "resume_file": str(args.resume_file)}, "limitations": limitations,
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{MODEL_ID}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    card_path = MODEL_CARDS / f"{MODEL_ID}.md"
    difference = comparison.get("difference")
    card_path.write_text("\n".join([
        "# Intracranial haemorrhage on head CT with neighbouring slices (RSNA ICH, 2.5-D, research)", "",
        f"- Data: RSNA ICH training set (PNG conversion), owner-confirmed licensed copy; {len(rows):,} slices; the single-slice model's patient split.",
        "- Input: the slice below, the slice and the slice above (by z within the series) as three channels.",
        f"- Held-out test: {len(y):,} slices of {len(np.unique(patients)):,} unseen patients; mean AUROC {report['mean_auroc']:.3f}; "
        f"study-level any-haemorrhage AUROC {study_level['auroc']:.3f}.",
        *([f"- Against the single-slice model on the same test slices: mean AUROC difference {difference:+.4f}."] if difference is not None else []),
        *[f"- {item['name']}: AUROC {item['auroc']:.3f}, sensitivity {item['sensitivity']:.3f}, specificity {item['specificity']:.3f}"
          for item in per_label.values()],
        "", "## Limitations", *[f"- {item}" for item in limitations], ""]), encoding="utf-8")
    register_model({
        "model_id": MODEL_ID, "display_name": "Intracranial haemorrhage on head CT series, neighbouring slices (RSNA ICH 2.5-D, research)",
        "domain": "medical_imaging", "task": "multilabel_image_classification", "anatomy": "brain", "framework": "torchvision efficientnet_b0",
        "adapter": "app.services.model_inference", "source_repository": "medtwin/training", "dependency_environment": ".venv",
        "weights_path": checkpoint_ref(checkpoint_path), "device": "cuda_or_cpu", "supported_inputs": ["application/dicom (ordered series)"],
        "supported_modalities": ["HEAD_CT_SERIES"], "supported_classes": [NAMES[key] for key in LABELS], "status": "READY_UNVALIDATED",
        "validated": False, "research_inference": True, "inference_input": "head_ct_series", "limitations": limitations,
        "dicom_window": single.DICOM_WINDOW, "context": CONTEXT,
        "artifact_bundle": {
            "dataset_version": version, "dataset_license": single.LICENSE["name"], "split_manifest_path": relative(single.MANIFEST),
            "ood_sample_manifest_path": relative(ood_manifest),
            "task_definition": "Per-slice presence of epidural, subdural, intraparenchymal, intraventricular and subarachnoid haemorrhage, and any, "
                               "from the slice and its two neighbours",
            "label_definition": {"source": "RSNA stage_2_train labels", "classes": [NAMES[key] for key in LABELS]},
            "preprocessing_version": "png-stack3-neighbours-resize256-imagenetnorm-v1", "checkpoint_path": checkpoint_ref(checkpoint_path),
            "checkpoint_sha256": checkpoint_sha, "calibration": None,
            "decision_thresholds": {NAMES[key]: round(value, 6) for key, value in thresholds.items()},
            "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(card_path),
        },
    })
    print(json.dumps({"mean_auroc": report["mean_auroc"], "study_any_auroc": study_level["auroc"], "difference_vs_single": difference}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
