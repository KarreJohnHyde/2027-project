"""PTB-XL 12-lead ECG diagnostic-superclass classifier (research), with an exact WFDB reader.

Data: PTB-XL 1.0.1 (CC BY 4.0), the 100 Hz records. Integrity is checked three ways:
every file used against the publisher's SHA256SUMS.txt, every lead against its header
checksum (16-bit sum of the samples) and first sample. Splits follow the publisher's
recommendation, strat_fold 1-8 train, 9 validation, 10 test (folds 9-10 carry
human-validated labels); patient disjointness of the three splits is asserted.

Labels: the five diagnostic superclasses (NORM, MI, STTC, CD, HYP), aggregated from the
record's SCP codes whose scp_statements row has diagnostic == 1 (multi-label, as in the
PTB-XL benchmark). Records without any superclass are excluded and counted.

Selection (macro AUROC), per-class Platt calibration and per-class decision thresholds
(maximum F1) use the validation fold only; the test fold is evaluated once, with
patient-level bootstrap CIs.

  python -m ml_training.ecg --model-id ptbxl_ecg_baseline
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

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, device, register_model, relative, set_seed
from ml_training.ptbxl import (  # noqa: F401  (re-exported for tests and callers)
    DATASET_DIR, LEADS, LICENSE, SUPERCLASSES, WfdbError, assert_patient_disjoint, dataset_version as ptbxl_dataset_version,
    load_metadata, publisher_checksums, read_header, read_record, used_files, verify_files,
)

sys.path.insert(0, str(ROOT / "backend"))
from app.services.evaluation_metrics import _auroc, _average_precision  # noqa: E402  (shared with the Validation Center)


class Block(nn.Module):
    def __init__(self, channels_in: int, channels_out: int, kernel: int, stride: int):
        super().__init__()
        self.body = nn.Sequential(
            nn.Conv1d(channels_in, channels_out, kernel, stride, kernel // 2, bias=False), nn.BatchNorm1d(channels_out), nn.ReLU(inplace=True),
            nn.Conv1d(channels_out, channels_out, kernel, 1, kernel // 2, bias=False), nn.BatchNorm1d(channels_out))
        self.shortcut = nn.Identity() if channels_in == channels_out and stride == 1 else nn.Sequential(
            nn.Conv1d(channels_in, channels_out, 1, stride, bias=False), nn.BatchNorm1d(channels_out))
        self.act = nn.ReLU(inplace=True)

    def forward(self, x):
        return self.act(self.body(x) + self.shortcut(x))


class ResNet1d(nn.Module):
    """Compact 1D residual network for 12 x 1000 inputs (10 s at 100 Hz)."""

    def __init__(self, classes: int, leads: int = 12):
        super().__init__()
        self.stem = nn.Sequential(nn.Conv1d(leads, 64, 15, 2, 7, bias=False), nn.BatchNorm1d(64), nn.ReLU(inplace=True), nn.MaxPool1d(3, 2, 1))
        self.layers = nn.Sequential(Block(64, 64, 7, 1), Block(64, 128, 5, 2), Block(128, 128, 5, 1), Block(128, 256, 3, 2), Block(256, 256, 3, 1))
        self.head = nn.Sequential(nn.Dropout(0.3), nn.Linear(512, classes))

    def forward(self, x):
        features = self.layers(self.stem(x))
        return self.head(torch.cat([features.mean(-1), features.amax(-1)], dim=1))


@torch.no_grad()
def predict_logits(model, x: torch.Tensor, dev, batch: int = 256) -> np.ndarray:
    model.eval()
    out = []
    for start in range(0, len(x), batch):
        with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
            out.append(model(x[start:start + batch].to(dev)).float().cpu())
    return torch.cat(out).numpy()


def macro_auroc(y: np.ndarray, score: np.ndarray) -> float | None:
    values = [_auroc(y[:, k], score[:, k]) for k in range(y.shape[1])]
    values = [value for value in values if value is not None]
    return float(np.mean(values)) if len(values) == y.shape[1] else None


def fit_platt(logits: np.ndarray, y: np.ndarray) -> list[tuple[float, float]]:
    params = []
    for k in range(y.shape[1]):
        a = torch.ones(1, requires_grad=True)
        b = torch.zeros(1, requires_grad=True)
        z, t = torch.tensor(logits[:, k]), torch.tensor(y[:, k], dtype=torch.float32)
        optimizer = torch.optim.LBFGS([a, b], lr=0.1, max_iter=200)

        def closure():
            optimizer.zero_grad()
            loss = nn.functional.binary_cross_entropy_with_logits(a * z + b, t)
            loss.backward()
            return loss

        optimizer.step(closure)
        params.append((float(a.item()), float(b.item())))
    return params


def apply_platt(logits: np.ndarray, params) -> np.ndarray:
    return np.stack([1 / (1 + np.exp(-(a * logits[:, k] + b))) for k, (a, b) in enumerate(params)], axis=1)


def ece(y: np.ndarray, p: np.ndarray, bins: int = 10) -> float:
    edges = np.linspace(0, 1, bins + 1)
    total = 0.0
    for low, high in zip(edges[:-1], edges[1:]):
        mask = (p >= low) & (p < high if high < 1 else p <= high)
        if mask.any():
            total += mask.mean() * abs(p[mask].mean() - y[mask].mean())
    return float(total)


def best_f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    best, chosen = -1.0, 0.5
    for threshold in np.unique(np.round(p, 4)):
        predicted = p >= threshold
        tp = int((predicted & (y == 1)).sum())
        fp = int((predicted & (y == 0)).sum())
        fn = int((~predicted & (y == 1)).sum())
        f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
        if f1 > best:
            best, chosen = f1, float(threshold)
    return chosen


def binary_stats(y: np.ndarray, predicted: np.ndarray) -> dict:
    tp = int((predicted & (y == 1)).sum())
    fp = int((predicted & (y == 0)).sum())
    fn = int((~predicted & (y == 1)).sum())
    tn = int((~predicted & (y == 0)).sum())
    ratio = lambda num, den: num / den if den else None  # noqa: E731
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn, "sensitivity": ratio(tp, tp + fn), "specificity": ratio(tn, tn + fp),
            "ppv": ratio(tp, tp + fp), "f1": ratio(2 * tp, 2 * tp + fp + fn)}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--model-id", default="ptbxl_ecg_baseline")
    parser.add_argument("--epochs", type=int, default=40)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--lr", type=float, default=1e-3)
    parser.add_argument("--weight-decay", type=float, default=1e-2)
    parser.add_argument("--seed", type=int, default=20261024)
    args = parser.parse_args()
    set_seed(args.seed)
    dev = device()
    run = Run(args.model_id, "ptbxl-diagnostic-superclass", vars(args))

    records, statements, excluded = load_metadata()
    disjoint = assert_patient_disjoint(records)
    sums = publisher_checksums()
    integrity = verify_files(used_files(records), sums)
    signals = np.stack([read_record(DATASET_DIR / f"{record['file']}.hea").T for record in records]).astype(np.float32)
    integrity["leads_checksum_and_first_sample_verified"] = len(records) * len(LEADS)
    dataset_version = ptbxl_dataset_version(records, sums)
    labels = np.array([[int(name in record["labels"]) for name in SUPERCLASSES] for record in records], dtype=np.float32)
    split = np.array([record["split"] for record in records])
    run.log(event="data", records=len(records), excluded=excluded, splits=dict(Counter(split)), integrity=integrity)

    mean = signals[split == "train"].mean(axis=(0, 2), keepdims=True)
    std = signals[split == "train"].std(axis=(0, 2), keepdims=True) + 1e-6
    tensor = torch.from_numpy((signals - mean) / std)
    parts = {name: (tensor[split == name], labels[split == name]) for name in ("train", "val", "test")}
    loader = DataLoader(TensorDataset(parts["train"][0], torch.from_numpy(parts["train"][1])), batch_size=args.batch_size, shuffle=True,
                        generator=torch.Generator().manual_seed(args.seed), drop_last=True)

    model = ResNet1d(len(SUPERCLASSES)).to(dev)
    optimizer = torch.optim.AdamW(model.parameters(), lr=args.lr, weight_decay=args.weight_decay)
    scheduler = torch.optim.lr_scheduler.OneCycleLR(optimizer, max_lr=args.lr, epochs=args.epochs, steps_per_epoch=len(loader))
    criterion = nn.BCEWithLogitsLoss()
    best_state, best_auroc, best_epoch = None, -1.0, 0
    for epoch in range(1, args.epochs + 1):
        model.train()
        running = 0.0
        for x, y in loader:
            x, y = x.to(dev), y.to(dev)
            # Mild, physiologically neutral augmentation: amplitude scaling and sensor-level noise.
            x = x * torch.empty(x.shape[0], 1, 1, device=dev).uniform_(0.9, 1.1) + 0.01 * torch.randn_like(x)
            with torch.autocast(dev.type, dtype=torch.bfloat16, enabled=dev.type == "cuda"):
                loss = criterion(model(x).float(), y)
            optimizer.zero_grad(set_to_none=True)
            loss.backward()
            optimizer.step()
            scheduler.step()
            running += float(loss)
        val_auroc = macro_auroc(parts["val"][1], predict_logits(model, parts["val"][0], dev))
        run.log(epoch=epoch, train_loss=round(running / len(loader), 4), val_macro_auroc=round(val_auroc, 4),
                gpu_peak_mib=int(torch.cuda.max_memory_allocated() / 2**20) if dev.type == "cuda" else 0)
        if val_auroc > best_auroc:
            best_state, best_auroc, best_epoch = copy.deepcopy({k: v.cpu() for k, v in model.state_dict().items()}), val_auroc, epoch
    model.load_state_dict(best_state)

    val_logits = predict_logits(model, parts["val"][0], dev)
    platt = fit_platt(val_logits, parts["val"][1])
    val_probability = apply_platt(val_logits, platt)
    thresholds = [best_f1_threshold(parts["val"][1][:, k], val_probability[:, k]) for k in range(len(SUPERCLASSES))]

    # Test fold, evaluated once with the frozen checkpoint, calibration and thresholds.
    test_logits = predict_logits(model, parts["test"][0], dev)
    y = parts["test"][1].astype(int)
    raw = 1 / (1 + np.exp(-test_logits))
    probability = apply_platt(test_logits, platt)
    predicted = probability >= np.array(thresholds)
    patients = np.array([record["patient_id"] for record in records if record["split"] == "test"])
    per_class = []
    for k, name in enumerate(SUPERCLASSES):
        stats = binary_stats(y[:, k], predicted[:, k])
        per_class.append({"class": name, "positives": int(y[:, k].sum()), "prevalence": float(y[:, k].mean()),
                          "auroc": _auroc(y[:, k], probability[:, k]), "auprc": _average_precision(y[:, k], probability[:, k]),
                          "auroc_95ci": bootstrap_ci(lambda idx, k=k: _auroc(y[idx, k], probability[idx, k]), len(y), patients),
                          "threshold_from_validation": thresholds[k], **stats,
                          "ece_raw": ece(y[:, k], raw[:, k]), "ece_platt": ece(y[:, k], probability[:, k])})
    macro_f1 = lambda idx: float(np.mean([binary_stats(y[idx, k], predicted[idx, k])["f1"] or 0.0 for k in range(len(SUPERCLASSES))]))  # noqa: E731
    metrics = {"macro_auroc": macro_auroc(y, probability), "macro_auprc": float(np.mean([item["auprc"] for item in per_class])),
               "macro_f1_at_validation_thresholds": macro_f1(np.arange(len(y))),
               "mean_ece_raw": float(np.mean([item["ece_raw"] for item in per_class])), "mean_ece_platt": float(np.mean([item["ece_platt"] for item in per_class]))}
    intervals = {"macro_auroc": bootstrap_ci(lambda idx: macro_auroc(y[idx], probability[idx]), len(y), patients),
                 "macro_f1_at_validation_thresholds": bootstrap_ci(macro_f1, len(y), patients)}
    for interval in intervals.values():
        interval["unit"] = "patient"
    for item in per_class:
        item["auroc_95ci"]["unit"] = "patient"

    checkpoint_path, checkpoint_sha = run.save_checkpoint({
        "kind": "ecg_classifier", "arch": "resnet1d_compact", "state_dict": best_state, "classes": SUPERCLASSES, "leads": LEADS,
        "sampling_rate_hz": 100, "samples": 1000, "lead_mean_mv": [float(v) for v in mean.ravel()], "lead_std_mv": [float(v) for v in std.ravel()],
        "platt": [[a, b] for a, b in platt], "thresholds": [float(t) for t in thresholds], "dataset_version": dataset_version,
        "preprocessing": "100 Hz PTB-XL records, 10 s; physical mV from WFDB gain/baseline; per-lead standardisation with training-fold mean/std",
    })
    predictions_path = run.directory / "predictions_test.csv"
    with predictions_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ecg_id", "patient_id", *[f"y_{name}" for name in SUPERCLASSES], *[f"p_{name}" for name in SUPERCLASSES]])
        for record, truth, probs in zip([r for r in records if r["split"] == "test"], y, probability):
            writer.writerow([record["ecg_id"], record["patient_id"], *truth.tolist(), *[f"{value:.6f}" for value in probs]])

    counts = {name: int((split == name).sum()) for name in ("train", "val", "test")}
    prevalence = {name: {cls: float(labels[split == name][:, k].mean()) for k, cls in enumerate(SUPERCLASSES)} for name in ("train", "val", "test")}
    limitations = [
        "Single-source internal evaluation (PTB-XL, Physikalisch-Technische Bundesanstalt, recordings 1989-1996); no external validation.",
        "Superclass labels aggregate cardiologist SCP statements; they are not adjudicated clinical diagnoses.",
        "Only 100 Hz, 10-second, 12-lead resting ECGs in the PTB-XL lead order are in scope; other devices, sampling rates or lead sets are out of distribution.",
        "Platt calibration was fitted on the validation fold of the same source; probabilities are not calibrated for any clinical population.",
        "Research-only output; not validated for clinical use.",
    ]
    report = {
        "model_id": args.model_id, "run_id": run.run_id, "task_id": "ptbxl-diagnostic-superclass", "task_type": "multilabel_classification",
        "dataset": "PTB-XL 1.0.1 (12-lead ECG, 100 Hz)", "dataset_id": "ptb-xl-1.0.1", "dataset_version": dataset_version, "dataset_license": LICENSE,
        "split_method": "publisher stratified folds: 1-8 train, 9 validation, 10 test (patient-disjoint, asserted)", "split_counts": counts,
        "patients": disjoint, "excluded_records": excluded, "label_prevalence": prevalence, "integrity": integrity, "classes": SUPERCLASSES,
        "test_n": int(len(y)), "test_patients": int(len(np.unique(patients))),
        "selection": {"criterion": "validation macro AUROC", "best_epoch": best_epoch, "val_macro_auroc": best_auroc},
        "calibration": {"method": "per-class Platt scaling", "fitted_on": "validation fold", "parameters": {name: list(p) for name, p in zip(SUPERCLASSES, platt)}},
        "decision_thresholds": {"rule": "per-class maximum F1 on the validation fold", "values": dict(zip(SUPERCLASSES, thresholds))},
        "metrics": metrics, "confidence_intervals_95": intervals, "per_class": per_class,
        "benchmark_context": "Strodthoff et al. 2020 (IEEE JBHI) report macro AUROC about 0.93 for the PTB-XL superdiagnostic task with 1D CNNs; "
                             "context only, not a comparison under identical conditions.",
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions_path),
        "training_seconds": run.elapsed_seconds, "config": vars(args),
        "reporting_context": {"dataset": "PTB-XL 1.0.1", "dataset_version": dataset_version[:16], "split": "test (strat_fold 10)", "checkpoint": f"sha256:{checkpoint_sha}"},
        "limitations": limitations,
    }
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    ci = lambda item: f"{item['low']:.3f}-{item['high']:.3f}" if item.get("status") == "COMPUTED" else "not computed"  # noqa: E731
    card = [
        "# Model card: PTB-XL 12-lead ECG diagnostic-superclass classifier (research)", "",
        f"- **Model id:** `{args.model_id}` (registry status `READY_UNVALIDATED`; research-only)",
        f"- **Task:** multi-label {', '.join(SUPERCLASSES)} from 10-second 100 Hz 12-lead resting ECGs.",
        f"- **Data:** PTB-XL 1.0.1 ({LICENSE['name']}). Dataset version `{dataset_version[:16]}`; {integrity['files_verified']} files verified against the publisher's SHA-256 sums; every lead checked against its header checksum.",
        f"- **Split:** publisher folds 1-8 / 9 / 10 ({counts['train']} / {counts['val']} / {counts['test']} records; patient-disjoint, asserted). {excluded.get('no_diagnostic_superclass', 0)} records without a diagnostic superclass excluded.",
        f"- **Architecture:** compact 1D ResNet trained from scratch; best validation epoch {best_epoch} (val macro AUROC {best_auroc:.3f}).",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.", "",
        "## Held-out test results (fold 10, evaluated once)", "",
        f"- Macro AUROC {metrics['macro_auroc']:.3f} (95% CI {ci(intervals['macro_auroc'])}); macro AUPRC {metrics['macro_auprc']:.3f}; macro F1 at validation thresholds {metrics['macro_f1_at_validation_thresholds']:.3f} (95% CI {ci(intervals['macro_f1_at_validation_thresholds'])}).",
        f"- n = {len(y)} ECGs from {len(np.unique(patients))} patients (bootstrap unit: patient).",
        "- Per class: " + "; ".join(f"{item['class']} AUROC {item['auroc']:.3f} (CI {ci(item['auroc_95ci'])}), sensitivity {item['sensitivity']:.2f}, specificity {item['specificity']:.2f}" for item in per_class) + ".",
        f"- Mean ECE {metrics['mean_ece_raw']:.3f} raw, {metrics['mean_ece_platt']:.3f} after Platt scaling.", "",
        "## Limitations", "", *[f"- {item}" for item in limitations], "", f"Full report: `{relative(report_path)}`.",
    ]
    (MODEL_CARDS / f"{args.model_id}.md").write_text("\n".join(card) + "\n", encoding="utf-8")

    register_model({
        "model_id": args.model_id, "display_name": "PTB-XL 12-lead ECG diagnostic-superclass classifier (research)", "domain": "cardiology",
        "task": "multilabel_ecg_classification", "anatomy": "heart", "framework": "pytorch", "adapter": "ml_training.ecg",
        "source_repository": "medtwin (ml_training/ecg.py)", "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path),
        "device": "cuda_or_cpu", "supported_inputs": ["application/wfdb (100 Hz, 12-lead, 10 s)"], "supported_modalities": ["ECG"],
        "inference_input": "ecg_12lead", "supported_classes": SUPERCLASSES, "status": "READY_UNVALIDATED", "validated": False, "processor_only": False,
        "research_inference": True, "limitations": limitations,
        "artifact_bundle": {
            "dataset_version": dataset_version, "dataset_license": LICENSE["name"], "split_manifest_path": relative(report_path),
            "task_definition": "Multi-label PTB-XL diagnostic superclasses from SCP statements with diagnostic == 1",
            "label_definition": {"source": "scp_statements.csv diagnostic_class", "classes": SUPERCLASSES},
            "preprocessing_version": "wfdb16-100hz-10s-leadstd-v1", "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha,
            "calibration": {"method": "per-class Platt scaling (validation fold)"}, "decision_thresholds": {"rule": "per-class max F1 (validation fold)", "values": dict(zip(SUPERCLASSES, thresholds))},
            "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions_path), "evaluation_report_path": relative(report_path),
            "model_card_path": relative(MODEL_CARDS / f"{args.model_id}.md"),
        },
    })
    run.log(event="done", test_macro_auroc=metrics["macro_auroc"], test_macro_f1=metrics["macro_f1_at_validation_thresholds"], checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
