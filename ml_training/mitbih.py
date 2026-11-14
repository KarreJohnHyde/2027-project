"""Research heartbeat classifier on the MIT-BIH Arrhythmia Database (PhysioNet, ODC-By 1.0), inter-patient evaluation.

Data: mit-bih-arrhythmia-database-1.0.0.zip from physionet.org (owner approval 2026-11-14; SHA-256 receipt next to the
archive). Read exactly, without the wfdb package: format-212 signals (two 12-bit samples in three bytes, checked against
the header checksum and first value) and MIT-format reference beat annotations (.atr).

Task: the AAMI EC57 beat classes from the reference annotations at their annotated positions:
  N  normal, left/right bundle branch block, atrial escape, nodal escape
  S  supraventricular ectopic (atrial premature, aberrated atrial premature, nodal premature, supraventricular premature)
  V  ventricular ectopic (premature ventricular contraction, ventricular escape)
  F  fusion of ventricular and normal
Paced records (102, 104, 107, 217) and unclassifiable/paced beats are excluded, as in de Chazal et al. 2004.

Split: the standard inter-patient division. DS1 (22 records) is development; 4 of its records (chosen with a seed,
keeping every class present) form the validation part used for model selection and early stopping. DS2 (22 other
patients) is the test set, scored once. No beat of a test patient is seen in training.

Input per beat: lead MLII at 360 Hz, 256 samples around the annotated R peak (90 before, 166 after), each beat standardised
by its own median and spread; plus RR features (previous RR, next RR, previous RR relative to the record's running mean of
the last 10 RR intervals). Note the RR features use the reference beat positions; a deployed system would need its own
beat detector, whose errors this evaluation does not include.

  python -m ml_training.mitbih
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
import random
import zipfile
from pathlib import Path

import numpy as np
import torch
from torch import nn

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, Run, bootstrap_ci, checkpoint_ref, register_model, relative, set_seed

ARCHIVE = Path("C:/MedTwin_Datasets/MIT_BIH/mit-bih-arrhythmia-database-1.0.0.zip")
PREFIX = "mit-bih-arrhythmia-database-1.0.0/"
SEED = 20261024
DS1 = [101, 106, 108, 109, 112, 114, 115, 116, 118, 119, 122, 124, 201, 203, 205, 207, 208, 209, 215, 220, 223, 230]
DS2 = [100, 103, 105, 111, 113, 117, 121, 123, 200, 202, 210, 212, 213, 214, 219, 221, 222, 228, 231, 232, 233, 234]
CLASSES = ["N", "S", "V", "F"]
# MIT annotation codes (wfdb ecgcodes.h) -> AAMI class.
AAMI = {1: "N", 2: "N", 3: "N", 34: "N", 11: "N", 8: "S", 4: "S", 7: "S", 9: "S", 5: "V", 10: "V", 6: "F"}
BEFORE, AFTER = 90, 166
LICENCE = "Open Data Commons Attribution License v1.0"


def read_header(text: str) -> dict:
    lines = [line for line in text.splitlines() if line.strip() and not line.startswith("#")]
    name, signals, frequency, samples = lines[0].split()[:4]
    leads = []
    for line in lines[1:1 + int(signals)]:
        tokens = line.split()
        gain = float(tokens[2].split("(")[0].split("/")[0])
        leads.append({"format": tokens[1], "gain": gain, "baseline": int(tokens[4]), "initial": int(tokens[5]), "checksum": int(tokens[6]),
                      "name": tokens[8] if len(tokens) > 8 else ""})
    return {"record": name, "signals": int(signals), "frequency": float(frequency), "samples": int(samples), "leads": leads}


def read_212(data: bytes, signals: int, samples: int) -> np.ndarray:
    """Format 212: every 3 bytes hold two 12-bit two's-complement samples."""
    raw = np.frombuffer(data, dtype=np.uint8)[: (samples * signals * 3 + 1) // 2]
    triples = raw[: len(raw) // 3 * 3].reshape(-1, 3).astype(np.int32)
    first = triples[:, 0] | ((triples[:, 1] & 0x0F) << 8)
    second = triples[:, 2] | ((triples[:, 1] & 0xF0) << 4)
    values = np.empty(triples.shape[0] * 2, dtype=np.int32)
    values[0::2], values[1::2] = first, second
    values = np.where(values > 2047, values - 4096, values)[: samples * signals]
    return values.reshape(samples, signals)


def read_annotations(data: bytes) -> list[tuple[int, int]]:
    """MIT annotation format: 16-bit little-endian words, code in the top 6 bits, time increment in the lower 10."""
    words = np.frombuffer(data[: len(data) // 2 * 2], dtype="<u2")
    result, time, index = [], 0, 0
    while index < len(words):
        word = int(words[index])
        code, value = word >> 10, word & 0x3FF
        index += 1
        if code == 0 and value == 0:
            break
        if code == 59:  # SKIP: a 32-bit interval follows, high 16 bits first
            time += (int(words[index]) << 16) | int(words[index + 1])
            index += 2
        elif code == 63:  # AUX: value bytes of text follow, padded to an even count
            index += (value + 1) // 2
        elif code in (60, 61, 62):  # NUM, SUB, CHN modify the previous annotation; no time
            continue
        else:
            time += value
            result.append((time, code))
    return result


def load_record(archive: zipfile.ZipFile, number: int) -> dict:
    header = read_header(archive.read(f"{PREFIX}{number}.hea").decode("ascii"))
    if any(lead["format"] != "212" for lead in header["leads"]):
        raise SystemExit(f"record {number}: only format 212 is expected")
    digital = read_212(archive.read(f"{PREFIX}{number}.dat"), header["signals"], header["samples"])
    for column, lead in enumerate(header["leads"]):
        if int(digital[0, column]) != lead["initial"] or int(digital[:, column].astype(np.int64).sum()) % 65536 != lead["checksum"] % 65536:
            raise SystemExit(f"record {number}: signal {lead['name']} fails the header checksum")
    column = next(i for i, lead in enumerate(header["leads"]) if lead["name"] == "MLII")
    lead = header["leads"][column]
    signal = (digital[:, column].astype(np.float32) - lead["baseline"]) / lead["gain"]
    return {"signal": signal, "frequency": header["frequency"], "annotations": read_annotations(archive.read(f"{PREFIX}{number}.atr"))}


def beats(record: dict, number: int) -> list[dict]:
    peaks = [(time, code) for time, code in record["annotations"] if code in AAMI or code in (12, 13, 38)]  # every beat, for RR intervals
    signal, rows = record["signal"], []
    rr = np.diff([time for time, _ in peaks]) / record["frequency"]
    for k in range(1, len(peaks) - 1):
        time, code = peaks[k]
        if code not in AAMI or time - BEFORE < 0 or time + AFTER > len(signal):
            continue
        window = signal[time - BEFORE: time + AFTER]
        centre, spread = np.median(window), np.percentile(window, 95) - np.percentile(window, 5)
        local = rr[max(0, k - 10): k]
        rows.append({"record": number, "time": int(time), "label": AAMI[code], "beat": ((window - centre) / (spread + 1e-6)).astype(np.float32),
                     "rr": np.array([rr[k - 1], rr[k], rr[k - 1] / (local.mean() + 1e-6)], dtype=np.float32)})
    return rows


class BeatNet(nn.Module):
    def __init__(self, classes: int):
        super().__init__()
        self.features = nn.Sequential(
            nn.Conv1d(1, 16, 7, padding=3), nn.BatchNorm1d(16), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(16, 32, 7, padding=3), nn.BatchNorm1d(32), nn.ReLU(), nn.MaxPool1d(2),
            nn.Conv1d(32, 64, 5, padding=2), nn.BatchNorm1d(64), nn.ReLU(), nn.AdaptiveAvgPool1d(8))
        self.head = nn.Sequential(nn.Linear(64 * 8 + 3, 64), nn.ReLU(), nn.Dropout(0.3), nn.Linear(64, classes))

    def forward(self, beat: torch.Tensor, rr: torch.Tensor) -> torch.Tensor:
        return self.head(torch.cat([self.features(beat.unsqueeze(1)).flatten(1), rr], dim=1))


def tensors(rows: list[dict]) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    return (torch.from_numpy(np.stack([row["beat"] for row in rows])), torch.from_numpy(np.stack([row["rr"] for row in rows])),
            torch.tensor([CLASSES.index(row["label"]) for row in rows]))


def predict(model: nn.Module, beat: torch.Tensor, rr: torch.Tensor) -> np.ndarray:
    model.eval()
    with torch.no_grad():
        return torch.cat([torch.softmax(model(beat[i:i + 2048], rr[i:i + 2048]), 1) for i in range(0, len(beat), 2048)]).numpy()


def class_metrics(y: np.ndarray, guess: np.ndarray) -> dict:
    result, f1s = {}, []
    for index, name in enumerate(CLASSES):
        tp = int(((guess == index) & (y == index)).sum())
        fn = int(((guess != index) & (y == index)).sum())
        fp = int(((guess == index) & (y != index)).sum())
        sensitivity = tp / (tp + fn) if tp + fn else None
        ppv = tp / (tp + fp) if tp + fp else None
        f1 = 2 * tp / (2 * tp + fp + fn) if tp + fp + fn else None
        result[name] = {"support": int((y == index).sum()), "sensitivity": sensitivity, "positive_predictive_value": ppv, "f1": f1}
        if f1 is not None and (y == index).any():
            f1s.append(f1)
    return {"per_class": result, "macro_f1": float(np.mean(f1s)), "accuracy": float((guess == y).mean()),
            "confusion_matrix": [[int(((y == t) & (guess == p)).sum()) for p in range(len(CLASSES))] for t in range(len(CLASSES))]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--epochs", type=int, default=30)
    parser.add_argument("--batch-size", type=int, default=256)
    args = parser.parse_args()
    receipt = ARCHIVE.with_name(ARCHIVE.name + ".receipt.json")
    if not receipt.exists():
        raise SystemExit("MIT-BIH archive or receipt missing; run scripts/acquire_approved_public_datasets.py --only mitdb")
    set_seed(SEED)
    torch.set_num_threads(max(1, torch.get_num_threads()))
    with zipfile.ZipFile(ARCHIVE) as archive:
        rows = {number: beats(load_record(archive, number), number) for number in DS1 + DS2}
    rng = random.Random(SEED)
    while True:  # 4 validation records from DS1 with every class present on both sides
        val_records = sorted(rng.sample(DS1, 4))
        train_records = [r for r in DS1 if r not in val_records]
        present = lambda records: {row["label"] for r in records for row in rows[r]}
        if present(val_records) >= set(CLASSES) - {"F"} and present(train_records) == set(CLASSES):
            break
    parts = {"train": [row for r in train_records for row in rows[r]], "val": [row for r in val_records for row in rows[r]],
             "test": [row for r in DS2 for row in rows[r]]}
    run = Run("ecg_mitbih_beat_classifier", "mitbih-aami-beats", {**vars(args), "validation_records": val_records})
    train_beat, train_rr, train_y = tensors(parts["train"])
    val_beat, val_rr, val_y = tensors(parts["val"])
    counts = torch.bincount(train_y, minlength=len(CLASSES)).float()
    weights = (counts.sum() / (len(CLASSES) * counts.clamp(min=1))).clamp(max=50.0)
    model = BeatNet(len(CLASSES))
    optimiser = torch.optim.AdamW(model.parameters(), lr=1e-3, weight_decay=1e-4)
    loss_fn = nn.CrossEntropyLoss(weight=weights)
    best, best_state, patience = -1.0, None, 0
    for epoch in range(args.epochs):
        model.train()
        order = torch.randperm(len(train_y))
        for start in range(0, len(order), args.batch_size):
            batch = order[start:start + args.batch_size]
            optimiser.zero_grad()
            loss = loss_fn(model(train_beat[batch], train_rr[batch]), train_y[batch])
            loss.backward()
            optimiser.step()
        val_metrics = class_metrics(val_y.numpy(), predict(model, val_beat, val_rr).argmax(1))
        run.log(epoch=epoch, val_macro_f1=val_metrics["macro_f1"], loss=float(loss))
        if val_metrics["macro_f1"] > best:
            best, best_state, patience = val_metrics["macro_f1"], {k: v.clone() for k, v in model.state_dict().items()}, 0
        else:
            patience += 1
            if patience >= 6:
                break
    model.load_state_dict(best_state)
    test_beat, test_rr, test_y = tensors(parts["test"])
    probabilities = predict(model, test_beat, test_rr)
    y, guess = test_y.numpy(), probabilities.argmax(1)
    metrics = class_metrics(y, guess)
    records = np.array([row["record"] for row in parts["test"]])
    intervals = {"macro_f1": bootstrap_ci(lambda idx: class_metrics(y[idx], guess[idx])["macro_f1"], len(y), records, unit="patient record")}
    for name in ("S", "V"):
        index = CLASSES.index(name)
        def sensitivity(idx, index=index):
            mask = y[idx] == index
            return float((guess[idx][mask] == index).mean()) if mask.any() else None
        intervals[f"{name}_sensitivity"] = bootstrap_ci(sensitivity, len(y), records, unit="patient record")
    checkpoint_path, checkpoint_sha = run.save_checkpoint({"kind": "ecg_beat_classifier", "arch": "BeatNet", "state_dict": model.state_dict(),
                                                           "classes": CLASSES, "window": [BEFORE, AFTER], "sampling_rate_hz": 360.0, "lead": "MLII",
                                                           "rr_features": ["previous_rr_s", "next_rr_s", "previous_rr_over_local_mean"]})
    predictions = run.directory / "predictions_test.csv"
    with predictions.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["record", "sample", "y_true", "y_pred", *[f"p_{name}" for name in CLASSES]])
        writer.writerows([[row["record"], row["time"], row["label"], CLASSES[g], *[f"{p:.5f}" for p in prob]]
                          for row, g, prob in zip(parts["test"], guess, probabilities)])
    dataset_version = json.loads(receipt.read_text(encoding="utf-8"))["sha256"]
    split_counts = {part: {name: sum(1 for row in items if row["label"] == name) for name in CLASSES} for part, items in parts.items()}
    limitations = [
        "Beat positions are the reference annotations; a deployed system needs its own beat detector, whose errors are not part of this evaluation.",
        "MIT-BIH holds 48 half-hour two-lead Holter records from 47 people (Boston, 1975-1979); the test part is 22 people.",
        "Single lead (MLII), 360 Hz only; other leads, sampling rates and devices are outside this model's evidence.",
        "Inter-patient supraventricular (S) beat detection is known to be hard; see the per-class sensitivity and its interval.",
        "Research-only output; not validated for clinical use.",
    ]
    report = {
        "model_id": "ecg_mitbih_beat_classifier", "run_id": run.run_id, "task_id": "mitbih-aami-beats", "task_type": "ecg_beat_classification",
        "dataset": "MIT-BIH Arrhythmia Database 1.0.0 (PhysioNet)", "dataset_id": "mitbih-arrhythmia-1.0.0", "dataset_version": dataset_version,
        "dataset_license": LICENCE, "split_method": "inter-patient DS1/DS2 (de Chazal 2004); 4 DS1 records for validation (seeded); paced records excluded",
        "records": {"train": train_records, "val": val_records, "test": DS2}, "split_counts": split_counts, "test_n": int(len(y)),
        "metrics": metrics, "confidence_intervals_95": intervals, "validation_macro_f1": best, "class_weights": weights.tolist(),
        "checkpoint": {"path": checkpoint_ref(checkpoint_path), "sha256": checkpoint_sha}, "held_out_predictions": checkpoint_ref(predictions),
        "limitations": limitations,
    }
    report_path = REPORTS / "ecg_mitbih_beat_classifier.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    per = metrics["per_class"]
    pct = lambda value: "n/a" if value is None else f"{value * 100:.1f}%"
    card = ["# Model card: Heartbeat class on single-lead ECG (MIT-BIH, inter-patient, research)", "",
            "- **Model id:** `ecg_mitbih_beat_classifier` (registry status `READY_UNVALIDATED`; research-only)",
            f"- **Data:** MIT-BIH Arrhythmia Database 1.0.0, PhysioNet ({LICENCE}).", f"- **Split:** {report['split_method']}.",
            f"- **Checkpoint:** `{checkpoint_ref(checkpoint_path)}`, SHA-256 `{checkpoint_sha}`.", "", "## Test results (22 unseen patients, evaluated once)", "",
            f"- Macro F1 {metrics['macro_f1']:.3f}; accuracy {metrics['accuracy']:.3f} on {len(y)} beats.",
            *[f"- {name}: support {per[name]['support']}, sensitivity {pct(per[name]['sensitivity'])}, positive predictive value {pct(per[name]['positive_predictive_value'])}."
              for name in CLASSES], "", "## Limitations", "", *[f"- {item}" for item in limitations], "", f"Full report: `{relative(report_path)}`."]
    (MODEL_CARDS / "ecg_mitbih_beat_classifier.md").write_text("\n".join(card) + "\n", encoding="utf-8")
    register_model({
        "model_id": "ecg_mitbih_beat_classifier", "display_name": "Heartbeat class on single-lead ECG (MIT-BIH, inter-patient, research)",
        "domain": "physiological_signals", "task": "ecg_beat_classification", "anatomy": "heart", "framework": "PyTorch 1-D CNN + RR features",
        "adapter": "ml_training.mitbih", "source_repository": "medtwin", "dependency_environment": ".venv", "weights_path": checkpoint_ref(checkpoint_path),
        "device": "cpu", "supported_inputs": ["WFDB format 212, lead MLII, 360 Hz, with reference beat positions"], "supported_modalities": ["ECG_HOLTER"],
        "inference_input": "ecg_beat_annotated", "supported_classes": CLASSES, "status": "READY_UNVALIDATED", "validated": False, "processor_only": False,
        "research_inference": True, "limitations": limitations,
        # A class the model claims but detects poorly on unseen patients keeps the whole model exploratory.
        "validation_readiness": {
            "validation_ready": False,
            "readiness": "INTERNAL_HELD_OUT_ONLY" if all((per[name]["sensitivity"] or 0) >= 0.5 for name in ("S", "V")) else "CLASS_NOT_DETECTED_ON_UNSEEN_PATIENTS",
            "run_scope": "RESEARCH" if all((per[name]["sensitivity"] or 0) >= 0.5 for name in ("S", "V")) else "EXPLORATORY_ONLY",
            "evidence": {"macro_f1": metrics["macro_f1"], "s_sensitivity": per["S"]["sensitivity"], "v_sensitivity": per["V"]["sensitivity"]},
        },
        "artifact_bundle": {
            "dataset_version": dataset_version, "dataset_license": LICENCE, "split_manifest_path": relative(report_path),
            "task_definition": "AAMI EC57 beat class (N, S, V, F) at each reference beat", "label_definition": {"classes": CLASSES, "source": "MIT-BIH reference annotations"},
            "preprocessing_version": "mitbih-mlii-360hz-256win-rr3-v1", "checkpoint_path": checkpoint_ref(checkpoint_path), "checkpoint_sha256": checkpoint_sha,
            "calibration": None, "decision_thresholds": {"rule": "argmax"}, "abstention_thresholds": None, "held_out_predictions_path": checkpoint_ref(predictions),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(MODEL_CARDS / "ecg_mitbih_beat_classifier.md"),
        },
    })
    run.log(event="done", macro_f1=metrics["macro_f1"], s_sensitivity=per["S"]["sensitivity"], v_sensitivity=per["V"]["sensitivity"], checkpoint_sha256=checkpoint_sha)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
