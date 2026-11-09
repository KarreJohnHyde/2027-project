"""How well the chest-radiograph model's Grad-CAM attention points at findings radiologists boxed (NIH ChestX-ray14).

Data: NIH ChestX-ray14 (NIH Clinical Center; no restrictions on use, attribution required), BBox_List_2017.csv:
984 boxes on 880 frontal radiographs for 8 findings, drawn by board-certified radiologists. The model
(TorchXRayVision DenseNet-121 "all") is third-party; its publisher trained it on NIH ChestX-ray14 among other
collections with image-level labels, never with these boxes. Whether a boxed image was among its training
images cannot be ruled out, so this measures localisation of attention, not classification accuracy.

For each box, attention is computed for the box's own finding by the serving function
(app.services.cxr_research.attention_for), with the rule fixed in advance (region: connected area around the
peak at >= 50% of the maximum). Metrics, per finding and overall, with patient-level bootstrap 95% CIs:

- pointing hit: the attention peak lies inside the radiologist's box; chance = box area / analysed area
  (a uniformly random point);
- IoU and IoBB (intersection over the attention box, as in Wang et al. CVPR 2017) of the attention box with the
  radiologist's box, and the share of boxes with IoU >= 0.1 / 0.25 / 0.5.

    python scripts/evaluate_cxr_attention_localisation.py
"""

from __future__ import annotations

import csv
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT))

from app.services import cxr_research  # noqa: E402
from ml_training.common import bootstrap_ci  # noqa: E402

LABELS = {"Atelectasis": "Atelectasis", "Cardiomegaly": "Cardiomegaly", "Effusion": "Effusion", "Infiltrate": "Infiltration",
          "Infiltration": "Infiltration", "Mass": "Mass", "Nodule": "Nodule", "Pneumonia": "Pneumonia", "Pneumothorax": "Pneumothorax"}


def _image_index() -> dict[str, Path]:
    index = {}
    for folder in sorted(ROOT.glob("images_0*")):
        for path in (folder / "images").glob("*.png"):
            index[path.name] = path
    return index


def _iou(a, b) -> tuple[float, float]:
    x1, y1, x2, y2 = max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3])
    inter = max(0.0, x2 - x1) * max(0.0, y2 - y1)
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    union = area_a + area_b - inter
    return (inter / union if union > 0 else 0.0), (inter / area_a if area_a > 0 else 0.0)


def _summary(rows: list[dict]) -> dict:
    patients = np.array([row["patient_id"] for row in rows])
    hits = np.array([row["pointing_hit"] for row in rows], dtype=float)
    chance = np.array([row["chance_hit"] for row in rows])
    iou = np.array([row["iou"] for row in rows])
    iobb = np.array([row["iobb"] for row in rows])
    above = np.array([row["score_above_operating_point"] for row in rows], dtype=float)
    ci = lambda values: bootstrap_ci(lambda idx: float(values[idx].mean()), len(values), patients, rounds=2000, unit="patient")  # noqa: E731
    return {"boxes": len(rows), "images": len({row["image"] for row in rows}), "patients": int(len(set(patients))),
            "pointing_hit_rate": float(hits.mean()), "pointing_hit_rate_95ci": ci(hits), "chance_hit_rate": float(chance.mean()),
            "hit_rate_minus_chance": float(hits.mean() - chance.mean()),
            "mean_iou": float(iou.mean()), "mean_iou_95ci": ci(iou), "mean_iobb": float(iobb.mean()),
            "iou_at_least": {str(t): float((iou >= t).mean()) for t in (0.1, 0.25, 0.5)},
            "iobb_at_least": {str(t): float((iobb >= t).mean()) for t in (0.25, 0.5)},
            "score_above_operating_point_rate": float(above.mean())}


def main() -> int:
    started = time.monotonic()
    index = _image_index()
    test_list = set((ROOT / "test_list.txt").read_text(encoding="utf-8").split()) if (ROOT / "test_list.txt").is_file() else set()
    boxes = []
    with (ROOT / "BBox_List_2017.csv").open(encoding="utf-8", newline="") as handle:
        reader = csv.reader(handle)
        next(reader)
        for row in reader:
            if not row or not row[0]:
                continue
            x, y, w, h = (float(value) for value in row[2:6])
            boxes.append({"image": row[0], "label": row[1].strip(), "box": [x, y, x + w, y + h]})
    by_image = defaultdict(list)
    for item in boxes:
        by_image[item["image"]].append(item)
    rows, missing = [], []
    for image_name, items in sorted(by_image.items()):
        path = index.get(image_name)
        if path is None:
            missing.append(image_name)
            continue
        with Image.open(path) as opened:
            image = opened.convert("L")
        findings = sorted({LABELS[item["label"]] for item in items})
        result = cxr_research.attention_for(image, findings)
        marks = {entry["finding"]: entry for entry in result["attention"]}
        left, top, side = result["analysis_square"]
        for item in items:
            finding = LABELS[item["label"]]
            entry = marks[finding]
            box = item["box"]
            peak = entry["peak_xy"]
            hit = peak is not None and box[0] <= peak[0] <= box[2] and box[1] <= peak[1] <= box[3]
            clipped = [max(box[0], left), max(box[1], top), min(box[2], left + side), min(box[3], top + side)]
            chance = max(0.0, clipped[2] - clipped[0]) * max(0.0, clipped[3] - clipped[1]) / float(side * side)
            iou, iobb = _iou(entry["region_box_xyxy"], box) if entry["region_box_xyxy"] else (0.0, 0.0)
            rows.append({"image": image_name, "patient_id": image_name.split("_")[0], "finding": finding, "nih_label": item["label"],
                         "official_split": "test" if image_name in test_list else "train_val", "reference_box_xyxy": [round(v, 1) for v in box],
                         "peak_xy": peak, "attention_box_xyxy": entry["region_box_xyxy"], "pointing_hit": bool(hit), "chance_hit": chance,
                         "iou": iou, "iobb": iobb, "score": result["scores"][finding],
                         "score_above_operating_point": result["scores"][finding] > cxr_research.OPERATING_POINT})
    per_finding = {finding: _summary([row for row in rows if row["finding"] == finding]) for finding in sorted({row["finding"] for row in rows})}
    overall = _summary(rows)
    splits = {split: sum(1 for row in rows if row["official_split"] == split) for split in ("test", "train_val")}
    report = {
        "evaluation": "Grad-CAM attention localisation against radiologist boxes (NIH ChestX-ray14 BBox_List_2017)",
        "model_id": cxr_research.MODEL_ID, "classifier_weights_sha256": cxr_research.WEIGHT_SHA256["classifier"],
        "dataset": "NIH ChestX-ray14 (NIH Clinical Center), BBox_List_2017.csv",
        "dataset_terms": "No restrictions on use; attribution required (link to the NIH download site, cite Wang et al. CVPR 2017, acknowledge the NIH Clinical Center).",
        "citation": "Wang X, Peng Y, Lu L, Lu Z, Bagheri M, Summers RM. ChestX-ray8. CVPR 2017.",
        "rule": cxr_research.ATTENTION_REGION_RULE, "rule_fixed_before_evaluation": True,
        "boxes_by_official_split": splits, "missing_images": len(missing),
        "caveats": [
            "The publisher trained the classifier on NIH ChestX-ray14 images with image-level labels (never these boxes); boxed images may have been among its training images.",
            "Attention shows where a score depends on; it is not a detector. A hit means the peak fell inside the radiologist's box.",
            "Scores were computed for each box's own finding whether or not the score was above the operating point.",
        ],
        "summary": {"overall": {key: overall[key] for key in ("boxes", "images", "patients", "pointing_hit_rate", "pointing_hit_rate_95ci",
                                                              "chance_hit_rate", "mean_iou", "iou_at_least")},
                    "per_finding": {finding: {"boxes": values["boxes"], "pointing_hit_rate": values["pointing_hit_rate"],
                                              "chance_hit_rate": values["chance_hit_rate"], "mean_iou": values["mean_iou"]}
                                    for finding, values in per_finding.items()}},
        "overall": overall, "per_finding": per_finding, "rows": rows, "seconds": round(time.monotonic() - started, 1),
    }
    cxr_research.LOCALISATION_REPORT.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"boxes": overall["boxes"], "hit_rate": round(overall["pointing_hit_rate"], 3), "chance": round(overall["chance_hit_rate"], 3),
                      "mean_iou": round(overall["mean_iou"], 3), "missing": len(missing), "splits": splits}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
