"""Intracranial haemorrhage on head CT slices: RSNA ICH (owner-confirmed licensed copy), multi-label.

Data: RSNA_PNG/rsna-ich-png.zip, the RSNA Intracranial Hemorrhage Detection training set as 752,763 single-window
512 x 512 greyscale PNG slices, with stage_2_train_labels.csv (epidural, subdural, intraparenchymal,
intraventricular, subarachnoid, any) and train_metadata.csv (pseudonymous patient, study and series ids). Slices
are read straight from the archive. Labels cover haemorrhage only: no ischaemic stroke, tumour or infection.

Protocol: whole patients are split train/validation/test 80/10/10 (seed). EfficientNet-B0 from ImageNet weights is
trained on train only; the epoch with the best mean validation AUROC is kept; each subtype's operating threshold
maximises Youden's J on validation; the frozen checkpoint reads the test patients once. Intervals resample patients.
Study-level "any haemorrhage" takes the highest slice probability of each study. Research use only.

    python -m ml_training.rsna_ich --epochs 3
"""

from __future__ import annotations

import argparse
import csv
import copy
import hashlib
import io
import json
import random
import sys
import zipfile
import zlib
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from torch import nn
from torch.utils.data import DataLoader, Dataset, get_worker_info
from torchvision import models, transforms

from ml_training.common import (MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, device, register_model, relative,
                                seed_worker, set_seed)

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import _auroc  # noqa: E402  (shared with the Validation Center)

MODEL_ID = "brain_ct_rsna_ich_classifier"
TASK_ID = "rsna-ich-slice-multilabel"
ARCHIVE = ROOT / "RSNA_PNG" / "rsna-ich-png.zip"
MANIFEST = ROOT / "_derived" / "datasets" / "rsna-ich" / "samples.csv"
LABELS = ("edh", "sdh", "iph", "ivh", "sah", "any")
NAMES = {"edh": "epidural", "sdh": "subdural", "iph": "intraparenchymal", "ivh": "intraventricular", "sah": "subarachnoid",
         "any": "any intracranial haemorrhage"}
MEAN, STD = [0.485, 0.456, 0.406], [0.229, 0.224, 0.225]
# How a DICOM slice is converted for this model (app.services.dicom_raster): the window the PNG archive was exported with.
# The width is measured, not assumed: integer HU through the export reach exactly 79 of the inner grey levels 1..254 in
# steps of 255/80, with truncation (docs/validation/RSNA_PNG_WINDOW_ESTIMATE.md). The level is not recoverable from
# quantisation; 40 HU (the standard brain level) matches the parenchyma and CSF peaks.
DICOM_WINDOW = {"center": 40, "width": 80, "function": "LINEAR_EXACT", "rounding": "floor",
                "source": "Width 80 HU measured from the training PNGs' grey-level quantisation (79 reachable levels, truncation); "
                          "level 40 HU estimated from the parenchyma and CSF peaks (docs/validation/RSNA_PNG_WINDOW_ESTIMATE.md)"}
LICENSE = {"status": "OWNER_CONFIRMED", "name": "RSNA Intracranial Hemorrhage Detection dataset terms (non-commercial research use)",
           "authorized_by": "repository owner (recorded interactive statement)", "authorized_on": "2026-11-04",
           "note": "The owner stated that this is the licensed RSNA download; the archive is a PNG conversion of the RSNA training set.",
           "citation": "Flanders AE, et al. Construction of a Machine Learning Dataset through Collaboration: The RSNA 2019 Brain CT "
                       "Hemorrhage Challenge. Radiol Artif Intell 2020;2(3):e190211."}


def read_samples(seed: int) -> list[dict]:
    """One row per labelled slice with its archive member, patient, study and split (whole patients per split)."""
    with zipfile.ZipFile(ARCHIVE) as archive:
        members = {}
        for name in archive.namelist():
            if name.endswith(".png"):
                members[name.rsplit("-", 1)[-1][:-4]] = name  # .../IM_0000-ID_45785016b.png -> ID_45785016b
        with archive.open("train_metadata.csv") as handle:
            meta = {row["SOPInstanceUID"]: row for row in csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8"))}
        with archive.open("stage_2_train_labels.csv") as handle:
            labels = list(csv.DictReader(io.TextIOWrapper(handle, encoding="utf-8")))
    rows = []
    for row in labels:
        sop = row["pid"]
        if sop not in members or sop not in meta:
            continue
        rows.append({"entry": members[sop], "patient": meta[sop]["PatientID"], "study": meta[sop]["StudyInstanceUID"],
                     **{key: int(row[key]) for key in LABELS}})
    patients = sorted({row["patient"] for row in rows})
    random.Random(seed).shuffle(patients)
    cut_val, cut_test = int(len(patients) * 0.8), int(len(patients) * 0.9)
    split = {patient: "train" if index < cut_val else "val" if index < cut_test else "test" for index, patient in enumerate(patients)}
    for row in rows:
        row["split"] = split[row["patient"]]
    return rows


def write_manifest(rows: list[dict]) -> str:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    fields = ["entry", "patient", "study", "split", *LABELS]
    digest = hashlib.sha256()
    with MANIFEST.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda item: item["entry"]):
            writer.writerow({field: row[field] for field in fields})
            digest.update(("\t".join(str(row[field]) for field in fields) + "\n").encode("utf-8"))
    return digest.hexdigest()


def member_locations(entries: list[str]) -> np.ndarray:
    """(local header offset, compressed size, compression method) per member, read once in the main process.
    Workers then read bytes directly; a ZipFile per worker would rebuild an index of 752,763 entries each."""
    with zipfile.ZipFile(ARCHIVE) as archive:
        info = {item.filename: item for item in archive.infolist()}
        return np.array([(info[name].header_offset, info[name].compress_size, info[name].compress_type) for name in entries], dtype=np.int64)


class SliceSet(Dataset):
    """Slices read from the archive by byte offset; each worker opens its own file handle."""

    def __init__(self, rows: list[dict], transform):
        self.locations = member_locations([row["entry"] for row in rows])
        self.targets = np.array([[row[key] for key in LABELS] for row in rows], dtype=np.float32)
        self.transform = transform
        self._handle = None
        self._owner = None

    def __len__(self) -> int:
        return len(self.locations)

    def _member(self, index: int) -> bytes:
        worker = get_worker_info()
        owner = worker.id if worker else -1
        if self._handle is None or self._owner != owner:
            self._handle, self._owner = ARCHIVE.open("rb"), owner
        offset, size, method = (int(value) for value in self.locations[index])
        self._handle.seek(offset)
        header = self._handle.read(30)  # local file header: name and extra-field lengths at bytes 26-29
        name_length, extra_length = int.from_bytes(header[26:28], "little"), int.from_bytes(header[28:30], "little")
        self._handle.seek(offset + 30 + name_length + extra_length)
        data = self._handle.read(size)
        if method == zipfile.ZIP_DEFLATED:
            return zlib.decompress(data, -15)
        if method == zipfile.ZIP_STORED:
            return data
        raise ValueError(f"unsupported zip compression method {method}")

    def __getitem__(self, index: int):
        image = Image.open(io.BytesIO(self._member(index))).convert("RGB")
        return self.transform(image), torch.from_numpy(self.targets[index])


def build_model() -> nn.Module:
    model = models.efficientnet_b0(weights=models.EfficientNet_B0_Weights.IMAGENET1K_V1)
    model.classifier[1] = nn.Linear(model.classifier[1].in_features, len(LABELS))
    return model


@torch.no_grad()
def predict(model: nn.Module, loader: DataLoader, dev) -> np.ndarray:
    model.eval()
    out = []
    for images, _ in loader:
        with torch.autocast(device_type=dev.type, dtype=torch.float16, enabled=dev.type == "cuda"):
            out.append(torch.sigmoid(model(images.to(dev, non_blocking=True)).float()).cpu().numpy())
    return np.concatenate(out)


def youden_threshold(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p)
    y_sorted, p_sorted = y[order], p[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    j = tp / max(1, y.sum()) - fp / max(1, (1 - y).sum())
    return float(p_sorted[int(np.argmax(j))])


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=3)
    parser.add_argument("--batch-size", type=int, default=64)
    parser.add_argument("--image-size", type=int, default=256)
    parser.add_argument("--lr", type=float, default=3e-4)
    parser.add_argument("--workers", type=int, default=6)
    parser.add_argument("--seed", type=int, default=20261104)
    parser.add_argument("--max-train-slices", type=int, default=0, help="0 = every training slice")
    args = parser.parse_args()
    set_seed(args.seed)
    rows = read_samples(args.seed)
    version = write_manifest(rows)
    splits = {name: [row for row in rows if row["split"] == name] for name in ("train", "val", "test")}
    train_rows = splits["train"]
    if args.max_train_slices and len(train_rows) > args.max_train_slices:
        train_rows = random.Random(args.seed).sample(train_rows, args.max_train_slices)
    run = Run(MODEL_ID, TASK_ID, {**vars(args), "dataset_version": version, "split_counts": {k: len(v) for k, v in splits.items()}})
    dev = device()
    train_tf = transforms.Compose([transforms.RandomResizedCrop(args.image_size, scale=(0.85, 1.0), ratio=(0.95, 1.05)),
                                   transforms.RandomHorizontalFlip(), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    # A few series are not square: the short side is resized and the centre kept, as at serving time.
    eval_tf = transforms.Compose([transforms.Resize(args.image_size), transforms.CenterCrop(args.image_size), transforms.ToTensor(),
                                  transforms.Normalize(MEAN, STD)])
    # Only the training loader keeps its workers alive across epochs; the evaluation loaders release theirs.
    loader_args = {"num_workers": args.workers, "pin_memory": True, "worker_init_fn": seed_worker}
    train_loader = DataLoader(SliceSet(train_rows, train_tf), batch_size=args.batch_size, shuffle=True, drop_last=True,
                              persistent_workers=args.workers > 0, **loader_args)
    val_set = SliceSet(splits["val"], eval_tf)
    val_loader = DataLoader(val_set, batch_size=args.batch_size * 2, **loader_args)
    model = build_model().to(dev)
    optimiser = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimiser, T_max=max(1, args.epochs * len(train_loader)))
    scaler = torch.amp.GradScaler(enabled=dev.type == "cuda")
    loss_fn = nn.BCEWithLogitsLoss()
    best = {"score": -1.0}
    for epoch in range(1, args.epochs + 1):
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
        probabilities = predict(model, val_loader, dev)
        aurocs = {key: _auroc(val_set.targets[:, i].astype(int), probabilities[:, i]) for i, key in enumerate(LABELS)}
        score = float(np.mean([value for value in aurocs.values() if value is not None]))
        run.log(epoch=epoch, train_loss=round(total / max(1, seen), 4), val_mean_auroc=round(score, 4), val_auroc={k: round(v, 4) for k, v in aurocs.items()})
        if score > best["score"]:
            best = {"score": score, "epoch": epoch, "state": copy.deepcopy(model.state_dict()), "val_probabilities": probabilities}
    model.load_state_dict(best["state"])
    thresholds = {key: youden_threshold(val_set.targets[:, i], best["val_probabilities"][:, i]) for i, key in enumerate(LABELS)}

    # The test patients are read exactly once, with the frozen selected checkpoint.
    test_set = SliceSet(splits["test"], eval_tf)
    p = predict(model, DataLoader(test_set, batch_size=args.batch_size * 2, **loader_args), dev)
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
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "image_multilabel_classifier", "arch": "efficientnet_b0", "state_dict": best["state"], "classes": [NAMES[key] for key in LABELS],
        "label_keys": list(LABELS), "image_size": args.image_size, "normalization": {"mean": MEAN, "std": STD}, "thresholds": thresholds,
        "task_id": TASK_ID, "dataset_version": version,
        "preprocessing": "single-window greyscale PNG as supplied, replicated to 3 channels; short side to 256 px, centre 256 x 256 crop; ImageNet normalisation",
    })
    predictions = run.directory / "predictions_test.csv"
    with predictions.open("w", encoding="utf-8") as handle:
        handle.write("entry,patient,study," + ",".join(f"y_{k}" for k in LABELS) + "," + ",".join(f"p_{k}" for k in LABELS) + "\n")
        for row, truth, probs in zip(splits["test"], y, p):
            handle.write(f"{row['entry']},{row['patient']},{row['study']}," + ",".join(map(str, truth)) + "," + ",".join(f"{v:.6f}" for v in probs) + "\n")
    limitations = [
        "Haemorrhage subtypes only (RSNA labels); no ischaemic stroke, tumour, infection or other pathology.",
        "Slice-level model on single-window PNGs; it does not see neighbouring slices or other CT windows.",
        "Internal held-out test on unseen patients of the same RSNA collection; no external validation.",
        "Operating thresholds come from the validation patients (Youden's J); probabilities are not calibrated for any clinical population.",
        "Research-only output; not validated for clinical use.",
    ]
    report = {
        "model_id": MODEL_ID, "run_id": run.run_id, "task_id": TASK_ID, "dataset": "RSNA Intracranial Hemorrhage Detection (PNG conversion)",
        "dataset_version": version, "dataset_license": LICENSE, "split_method": f"whole patients 80/10/10, seed {args.seed}",
        "split_counts": {name: len(items) for name, items in splits.items()}, "train_slices_used": len(train_rows),
        "patients_per_split": {name: len({row["patient"] for row in items}) for name, items in splits.items()},
        "selection": {"criterion": "mean validation AUROC over the six labels", "best_epoch": best["epoch"], "val_mean_auroc": best["score"]},
        "test_n": int(len(y)), "test_patients": int(len(np.unique(patients))), "group_unit": "patient",
        "per_label": per_label, "mean_auroc": float(np.mean([item["auroc"] for item in per_label.values()])), "study_level_any": study_level,
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions),
        "training_seconds": run.elapsed_seconds, "config": vars(args), "limitations": limitations,
        "reporting_context": {"dataset": "RSNA ICH", "dataset_version": version[:16], "split": "test", "checkpoint": f"sha256:{checkpoint_sha}",
                              "reporting_status": "INTERNAL_HELD_OUT"},
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{MODEL_ID}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    card_path = MODEL_CARDS / f"{MODEL_ID}.md"
    card_path.write_text("\n".join([
        "# Intracranial haemorrhage on head CT slices (RSNA ICH, research)", "",
        f"- Data: RSNA ICH training set (PNG conversion), owner-confirmed licensed copy; {len(rows):,} slices; whole patients 80/10/10.",
        f"- Held-out test: {len(y):,} slices of {len(np.unique(patients)):,} unseen patients; mean AUROC {report['mean_auroc']:.3f}; "
        f"study-level any-haemorrhage AUROC {study_level['auroc']:.3f}.",
        *[f"- {item['name']}: AUROC {item['auroc']:.3f}, sensitivity {item['sensitivity']:.3f}, specificity {item['specificity']:.3f}"
          for item in per_label.values()],
        "", "## Limitations", *[f"- {item}" for item in limitations], ""]), encoding="utf-8")
    register_model({
        "model_id": MODEL_ID, "display_name": "Intracranial haemorrhage on head CT slices, 5 subtypes (RSNA ICH, research)",
        "domain": "medical_imaging", "task": "multilabel_image_classification", "anatomy": "brain", "framework": "torchvision efficientnet_b0",
        "adapter": "app.services.model_inference", "source_repository": "medtwin/training", "dependency_environment": ".venv",
        "weights_path": checkpoint_ref(checkpoint_path), "device": "cuda_or_cpu", "supported_inputs": ["image/png", "image/jpeg"],
        "supported_modalities": ["HEAD_CT"], "supported_classes": [NAMES[key] for key in LABELS], "status": "READY_UNVALIDATED",
        "validated": False, "research_inference": True, "inference_input": "image_2d", "limitations": limitations,
        "dicom_window": DICOM_WINDOW,
        "artifact_bundle": {
            "dataset_version": version, "dataset_license": LICENSE["name"], "split_manifest_path": relative(MANIFEST),
            "task_definition": "Per-slice presence of epidural, subdural, intraparenchymal, intraventricular and subarachnoid haemorrhage, and any",
            "label_definition": {"source": "RSNA stage_2_train labels", "classes": [NAMES[key] for key in LABELS]},
            "preprocessing_version": "png-gray3-resize256-imagenetnorm-v1", "checkpoint_path": checkpoint_ref(checkpoint_path),
            "checkpoint_sha256": checkpoint_sha, "calibration": None,
            "decision_thresholds": {NAMES[key]: round(value, 6) for key, value in thresholds.items()},
            "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(card_path),
        },
    })
    print(json.dumps({"mean_auroc": report["mean_auroc"], "study_any_auroc": study_level["auroc"]}), flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
