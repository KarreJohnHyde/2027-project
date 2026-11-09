"""Multimodal fusion experiment: 12-lead ECG plus age and sex (PTB-XL 1.0.1, CC BY 4.0).

Two arms are trained with identical data order, augmentation, epochs and seed, and evaluated once on the
publisher's test fold (strat_fold 10; folds 1-8 train, 9 validation; patient-disjoint, asserted):

  ecg_only   the compact 1D ResNet of ml_training.ecg
  fusion     the same ECG network with a small age/sex branch joined before the classifier (intermediate fusion)

The comparison is paired: macro AUROC and per-class AUROC differences (fusion minus ECG only) with
patient-level bootstrap 95% intervals on the same test records. Calibration (Platt) and per-class maximum-F1
thresholds come from the validation fold only.

Demographic encoding (as served): age in years / 100, clipped to 0-0.9 (PTB-XL records ages of 90 and over as
300, which maps to 0.9), an age-missing flag, female = 1 / male = 0, and a sex-missing flag (value 0.5).

  python -m ml_training.ecg_fusion --model-id ptbxl_ecg_demographic_fusion
"""

from __future__ import annotations

import argparse
import copy
import csv
import json
import sys
from collections import Counter

import numpy as np
import torch
from torch import nn
from torch.utils.data import DataLoader, TensorDataset

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, device, relative, set_seed
from ml_training.ecg import ResNet1d, apply_platt, best_f1_threshold, binary_stats, fit_platt, macro_auroc
from ml_training.ptbxl import (
    DATASET_DIR, LEADS, LICENSE, SUPERCLASSES, assert_patient_disjoint, dataset_version as ptbxl_dataset_version,
    load_metadata, publisher_checksums, read_record, used_files, verify_files,
)

sys.path.insert(0, str(ROOT / "backend"))
from app.services.ecg_inference import demographic_vector  # noqa: E402  (the served encoding)
from app.services.evaluation_metrics import _auroc, _average_precision  # noqa: E402


class FusionNet(nn.Module):
    """ECG features (mean and max pooled, 512) joined with a 16-unit age/sex embedding."""

    def __init__(self, classes: int, leads: int = 12, demographic_features: int = 4):
        super().__init__()
        base = ResNet1d(classes, leads)
        self.stem, self.layers = base.stem, base.layers
        self.demographics = nn.Sequential(nn.Linear(demographic_features, 16), nn.ReLU(inplace=True))
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(512 + 16, classes))

    def forward(self, x, demographics):
        features = self.layers(self.stem(x))
        pooled = torch.cat([features.mean(-1), features.amax(-1)], dim=1)
        return self.head(torch.cat([pooled, self.demographics(demographics)], dim=1))


def demographics_by_ecg() -> dict[int, dict]:
    values = {}
    with (DATASET_DIR / "ptbxl_database.csv").open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            age = row.get("age", "").strip()
            sex = row.get("sex", "").strip()
            values[int(row["ecg_id"])] = {"age_years": float(age) if age else None,
                                          "sex": {"0": "M", "0.0": "M", "1": "F", "1.0": "F"}.get(sex)}
    return values


@torch.no_grad()
def logits_of(model, x, demographics, dev, batch: int = 256) -> np.ndarray:
    model.eval()
    out = []
    for start in range(0, len(x), batch):
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            chunk = x[start:start + batch].to(dev)
            result = model(chunk) if demographics is None else model(chunk, demographics[start:start + batch].to(dev))
        out.append(result.float().cpu())
    return torch.cat(out).numpy()


def train_arm(arm: str, parts: dict, args, dev, run: Run):
    set_seed(args.seed)
    model = (FusionNet(len(SUPERCLASSES)) if arm == "fusion" else ResNet1d(len(SUPERCLASSES))).to(dev)
    x, d, y = parts["train"]
    loader = DataLoader(TensorDataset(x, d, torch.from_numpy(y)), batch_size=args.batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(args.seed), drop_last=True)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, epochs=args.epochs, steps_per_epoch=len(loader))
    criterion = nn.BCEWithLogitsLoss()
    best_state, best_auroc, best_epoch = None, -1.0, 0
    noise = torch.Generator(device=dev).manual_seed(args.seed)
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for xb, db, yb in loader:
            xb, db, yb = xb.to(dev), db.to(dev), yb.to(dev)
            scale = torch.empty(xb.shape[0], 1, 1, device=dev).uniform_(0.9, 1.1, generator=noise)
            xb = xb * scale + 0.01 * torch.randn(xb.shape, device=dev, generator=noise)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                output = model(xb, db) if arm == "fusion" else model(xb)
                loss = criterion(output.float(), yb)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            running += float(loss)
        val_auroc = macro_auroc(parts["val"][2], logits_of(model, parts["val"][0], parts["val"][1] if arm == "fusion" else None, dev))
        run.log(arm=arm, epoch=epoch, train_loss=round(running / len(loader), 4), val_macro_auroc=round(val_auroc, 4))
        if val_auroc > best_auroc:
            best_state, best_auroc, best_epoch = copy.deepcopy({k: v.cpu() for k, v in model.state_dict().items()}), val_auroc, epoch
    model.load_state_dict(best_state)
    return model, best_state, best_auroc, best_epoch


def evaluate_arm(model, arm: str, parts: dict, dev) -> dict:
    use = (lambda name: parts[name][1]) if arm == "fusion" else (lambda name: None)
    val_logits = logits_of(model, parts["val"][0], use("val"), dev)
    platt = fit_platt(val_logits, parts["val"][2])
    val_probability = apply_platt(val_logits, platt)
    thresholds = [best_f1_threshold(parts["val"][2][:, k], val_probability[:, k]) for k in range(len(SUPERCLASSES))]
    probability = apply_platt(logits_of(model, parts["test"][0], use("test"), dev), platt)
    return {"platt": platt, "thresholds": thresholds, "probability": probability}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="ptbxl_ecg_demographic_fusion")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-2)
    parser.add_argument("--seed", type=int, default=20261024)
    args = parser.parse_args()
    dev = device()
    run = Run(args.model_id, "ptbxl-diagnostic-superclass-ecg-demographic-fusion", vars(args))

    records, _statements, excluded = load_metadata()
    disjoint = assert_patient_disjoint(records)
    sums = publisher_checksums()
    integrity = verify_files(used_files(records), sums)
    signals = np.stack([read_record(DATASET_DIR / f"{record['file']}.hea").T for record in records]).astype(np.float32)
    dataset_version = ptbxl_dataset_version(records, sums)
    labels = np.array([[int(name in record["labels"]) for name in SUPERCLASSES] for record in records], dtype=np.float32)
    split = np.array([record["split"] for record in records])
    demographic_rows = demographics_by_ecg()
    raw_demographics = [demographic_rows[record["ecg_id"]] for record in records]
    vectors = np.array([demographic_vector(item["age_years"], item["sex"]) for item in raw_demographics], dtype=np.float32)
    coverage = {"age_missing": int(sum(item["age_years"] is None for item in raw_demographics)),
                "sex_missing": int(sum(item["sex"] is None for item in raw_demographics)),
                "age_90_or_over_coded_300": int(sum((item["age_years"] or 0) >= 300 for item in raw_demographics))}
    run.log(event="data", records=len(records), excluded=excluded, splits=dict(Counter(split)), demographics=coverage)

    mean = signals[split == "train"].mean(axis=(0, 2), keepdims=True)
    std = signals[split == "train"].std(axis=(0, 2), keepdims=True) + 1e-6
    tensor = torch.from_numpy((signals - mean) / std)
    demographic_tensor = torch.from_numpy(vectors)
    parts = {name: (tensor[split == name], demographic_tensor[split == name], labels[split == name]) for name in ("train", "val", "test")}

    arms = {}
    for arm in ("ecg_only", "fusion"):
        model, state, best_auroc, best_epoch = train_arm(arm, parts, args, dev, run)
        arms[arm] = {"model": model, "state": state, "best_validation_macro_auroc": best_auroc, "best_epoch": best_epoch, **evaluate_arm(model, arm, parts, dev)}

    y = parts["test"][2].astype(int)
    patients = np.array([record["patient_id"] for record in records if record["split"] == "test"])
    results = {}
    for arm, item in arms.items():
        probability = item["probability"]
        predicted = probability >= np.array(item["thresholds"])
        per_class = []
        for k, name in enumerate(SUPERCLASSES):
            per_class.append({"class": name, "positives": int(y[:, k].sum()), "auroc": _auroc(y[:, k], probability[:, k]),
                              "auprc": _average_precision(y[:, k], probability[:, k]),
                              "auroc_95ci": bootstrap_ci(lambda idx, k=k, p=probability: _auroc(y[idx, k], p[idx, k]), len(y), patients, unit="patient"),
                              "threshold_from_validation": item["thresholds"][k], **binary_stats(y[:, k], predicted[:, k])})
        results[arm] = {"macro_auroc": macro_auroc(y, probability),
                        "macro_auroc_95ci": bootstrap_ci(lambda idx, p=probability: macro_auroc(y[idx], p[idx]), len(y), patients, unit="patient"),
                        "macro_auprc": float(np.mean([entry["auprc"] for entry in per_class])),
                        "macro_f1_at_validation_thresholds": float(np.mean([entry["f1"] or 0.0 for entry in per_class])),
                        "best_epoch": item["best_epoch"], "best_validation_macro_auroc": item["best_validation_macro_auroc"], "per_class": per_class}
    fused, alone = arms["fusion"]["probability"], arms["ecg_only"]["probability"]
    difference = {
        "definition": "fusion minus ECG only, same test records; percentile bootstrap over patients (paired)",
        "macro_auroc": results["fusion"]["macro_auroc"] - results["ecg_only"]["macro_auroc"],
        "macro_auroc_95ci": bootstrap_ci(lambda idx: macro_auroc(y[idx], fused[idx]) - macro_auroc(y[idx], alone[idx]), len(y), patients, unit="patient"),
        "per_class": {name: {"auroc": _auroc(y[:, k], fused[:, k]) - _auroc(y[:, k], alone[:, k]),
                             "auroc_95ci": bootstrap_ci(lambda idx, k=k: _auroc(y[idx, k], fused[idx, k]) - _auroc(y[idx, k], alone[idx, k]),
                                                        len(y), patients, unit="patient")}
                      for k, name in enumerate(SUPERCLASSES)},
    }
    interval = difference["macro_auroc_95ci"]
    difference["conclusion"] = ("FUSION_BETTER" if interval.get("low", 0) > 0 else "ECG_ONLY_BETTER" if interval.get("high", 0) < 0
                                else "NO_DIFFERENCE_SHOWN")
    run.log(event="test", ecg_only=results["ecg_only"]["macro_auroc"], fusion=results["fusion"]["macro_auroc"], difference=difference["macro_auroc"],
            ci=[interval.get("low"), interval.get("high")])

    test_records = [record for record in records if record["split"] == "test"]
    predictions_path = run.directory / "predictions_test.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ecg_id", "patient_id", *[f"label_{name}" for name in SUPERCLASSES],
                         *[f"ecg_only_p_{name}" for name in SUPERCLASSES], *[f"fusion_p_{name}" for name in SUPERCLASSES]])
        for index, record in enumerate(test_records):
            writer.writerow([record["ecg_id"], record["patient_id"], *y[index].tolist(),
                             *[round(float(value), 6) for value in alone[index]], *[round(float(value), 6) for value in fused[index]]])

    fusion = arms["fusion"]
    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "ecg_classifier", "arch": "resnet1d_compact_demographic_fusion", "state_dict": fusion["state"], "classes": SUPERCLASSES,
        "leads": LEADS, "sampling_rate_hz": 100, "samples": 1000, "lead_mean_mv": [float(v) for v in mean.ravel()],
        "lead_std_mv": [float(v) for v in std.ravel()], "platt": [[a, b] for a, b in fusion["platt"]],
        "thresholds": [float(t) for t in fusion["thresholds"]], "dataset_version": dataset_version,
        "demographic_encoding": "app.services.ecg_inference.demographic_vector v1: [age/100 clipped 0-0.9, age missing, female, sex missing]",
        "preprocessing": "100 Hz PTB-XL records, 10 s; physical mV from WFDB gain/baseline; per-lead standardisation with training-fold mean/std",
    })
    report = {
        "model_id": args.model_id, "run_id": run.run_id, "task_type": "multilabel_ecg_classification", "fusion": "intermediate (ECG features + age/sex embedding)",
        "dataset": "PTB-XL 1.0.1", "dataset_license": LICENSE, "dataset_version": dataset_version, "integrity": integrity, "patient_disjointness": disjoint,
        "split_method": "publisher stratified folds: 1-8 train, 9 validation, 10 test (patient-disjoint, asserted)",
        "split_counts": dict(Counter(split)), "excluded": excluded, "demographic_coverage": coverage,
        "test_n": int(len(y)), "metrics": {"macro_auroc": results["fusion"]["macro_auroc"], "macro_auprc": results["fusion"]["macro_auprc"],
                                            "macro_f1_at_validation_thresholds": results["fusion"]["macro_f1_at_validation_thresholds"]},
        "confidence_intervals_95": {"macro_auroc": results["fusion"]["macro_auroc_95ci"]},
        "arms": results, "paired_difference": difference,
        "calibration": {"method": "per-class Platt scaling", "fitted_on": "validation fold"},
        "decision_thresholds": {"rule": "per-class maximum F1 on the validation fold", "values": dict(zip(SUPERCLASSES, fusion["thresholds"]))},
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha},
        "held_out_predictions": checkpoint_ref(predictions_path),
        "limitations": [
            "One public source (PTB-XL, Germany, 1989-1996); no external or clinical validation.",
            "Superclasses are ECG annotation groups, not confirmed clinical diagnoses.",
            "Age and sex are the only non-ECG inputs; the served model needs both from the case's reviewed demographics or the request.",
        ],
    }
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    run.log(event="done", report=relative(report_path), checkpoint_sha256=checkpoint_sha, conclusion=difference["conclusion"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
