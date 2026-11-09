"""Re-select the RSNA ICH model's per-label thresholds on validation by F1, and report both operating points.

The first report used Youden's J, which for rare labels gave thresholds near zero (epidural 0.003): about 1 in 28
epidural flags was a bleed. F1 balances sensitivity against precision. Thresholds come from the validation
patients only (their probabilities are recomputed with the frozen checkpoint); the test figures are recomputed from
the test predictions saved at evaluation, so the test images are not read again. The checkpoint gains the new
thresholds (new hash), and the report, model card and registry entry are updated, with the change recorded.

    python -m ml_training.rsna_ich_operating_points
"""

from __future__ import annotations

import csv
import json
import sys

import numpy as np
import torch
from torch.utils.data import DataLoader
from torchvision import transforms

from ml_training.common import REPORTS, ROOT, checkpoint_ref, device, seed_worker, sha256_file
from ml_training.rsna_ich import LABELS, MANIFEST, MEAN, MODEL_ID, NAMES, STD, SliceSet, build_model, predict


def f1_threshold(y: np.ndarray, p: np.ndarray) -> float:
    order = np.argsort(-p)
    y_sorted, p_sorted = y[order], p[order]
    tp = np.cumsum(y_sorted)
    fp = np.cumsum(1 - y_sorted)
    f1 = 2 * tp / (2 * tp + fp + (y.sum() - tp))
    return float(p_sorted[int(np.argmax(f1))])


def operating_point(y: np.ndarray, p: np.ndarray, threshold: float) -> dict:
    guess = p >= threshold
    tp, fp = int((guess & (y == 1)).sum()), int((guess & (y == 0)).sum())
    fn, tn = int((~guess & (y == 1)).sum()), int((~guess & (y == 0)).sum())
    return {"threshold": round(threshold, 6), "sensitivity": tp / max(1, tp + fn), "specificity": tn / max(1, tn + fp),
            "ppv": tp / max(1, tp + fp), "f1": 2 * tp / max(1, 2 * tp + fp + fn), "flagged_slices": tp + fp}


def main() -> int:
    report_path = REPORTS / f"{MODEL_ID}.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    checkpoint = ROOT / report["checkpoint"]["path"]
    payload = torch.load(checkpoint, map_location="cpu", weights_only=True)
    dev = device()
    model = build_model()
    model.load_state_dict(payload["state_dict"])
    model.to(dev)
    with MANIFEST.open(encoding="utf-8", newline="") as handle:
        rows = [{**row, **{key: int(row[key]) for key in LABELS}} for row in csv.DictReader(handle) if row["split"] == "val"]
    size = payload["image_size"]
    eval_tf = transforms.Compose([transforms.Resize(size), transforms.CenterCrop(size), transforms.ToTensor(), transforms.Normalize(MEAN, STD)])
    val_set = SliceSet(rows, eval_tf)
    val_p = predict(model, DataLoader(val_set, batch_size=128, num_workers=6, pin_memory=True, worker_init_fn=seed_worker), dev)
    thresholds = {key: f1_threshold(val_set.targets[:, i], val_p[:, i]) for i, key in enumerate(LABELS)}

    with (ROOT / report["held_out_predictions"]).open(encoding="utf-8") as handle:
        test = list(csv.DictReader(handle))
    for key in LABELS:
        y = np.array([int(row[f"y_{key}"]) for row in test])
        p = np.array([float(row[f"p_{key}"]) for row in test])
        item = report["per_label"][key]
        youden = operating_point(y, p, float(payload["thresholds"][key]))
        f1 = operating_point(y, p, thresholds[key])
        item.update({"threshold_from_validation": f1["threshold"], "sensitivity": f1["sensitivity"], "specificity": f1["specificity"],
                     "ppv": f1["ppv"], "f1": f1["f1"], "flagged_slices": f1["flagged_slices"],
                     "operating_point": "F1 on the validation patients", "youden_operating_point": youden})
    payload["thresholds"] = thresholds
    payload["threshold_rule"] = "per label, maximum F1 on the validation patients"
    torch.save(payload, checkpoint)
    sha = sha256_file(checkpoint)
    report["checkpoint"]["sha256"] = sha
    report["reporting_context"]["checkpoint"] = f"sha256:{sha}"
    report.setdefault("report_corrections", []).append({
        "date": "2026-11-04", "change": "Operating thresholds re-selected on the validation patients by F1 (Youden's J kept as youden_operating_point): "
        "Youden's J gave near-zero thresholds for rare labels. AUROC values unchanged; test images not re-read; checkpoint hash changed."})
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    card = ROOT / "docs" / "models" / f"{MODEL_ID}.md"
    lines = card.read_text(encoding="utf-8").splitlines()
    keep = [line for line in lines if not any(line.startswith(f"- {NAMES[key]}:") for key in LABELS)]
    at = keep.index("") if "" in keep else len(keep)
    rows_text = [f"- {item['name']}: AUROC {item['auroc']:.3f}; at the F1 threshold {item['threshold_from_validation']:.3f}: sensitivity "
                 f"{item['sensitivity']:.3f}, specificity {item['specificity']:.3f}, PPV {item['ppv']:.3f}" for item in report["per_label"].values()]
    card.write_text("\n".join(keep[:at] + rows_text + keep[at:]) + "\n", encoding="utf-8")

    registry_path = ROOT / "model_registry" / "models.json"
    registry = json.loads(registry_path.read_bytes().decode("utf-8"))
    for entry in registry["models"]:
        if entry["model_id"] == MODEL_ID:
            entry["artifact_bundle"]["checkpoint_sha256"] = sha
            entry["artifact_bundle"]["decision_thresholds"] = {NAMES[key]: round(value, 6) for key, value in thresholds.items()}
            entry["limitations"] = [item.replace("Operating thresholds come from the validation patients (Youden's J)",
                                                 "Operating thresholds come from the validation patients (maximum F1)") for item in entry["limitations"]]
    registry_path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").encode("utf-8"))
    print(json.dumps({key: {k: round(v, 3) for k, v in report["per_label"][key].items() if k in ("threshold_from_validation", "sensitivity", "specificity", "ppv")}
                      for key in LABELS}, indent=1))
    print("checkpoint", checkpoint_ref(checkpoint), sha[:16])
    return 0


if __name__ == "__main__":
    sys.exit(main())
