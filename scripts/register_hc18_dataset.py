"""Register HC18 (fetal head circumference, Zenodo 1327317, CC BY 4.0) for head segmentation and measurement.

The publisher's training set has 999 2-D ultrasound images, each with an ellipse outline drawn by a sonographer and a
reference head circumference in mm with its pixel size (training_set_pixel_size_and_HC.csv). The unlabelled challenge
test set is not used. Outlines are filled into head masks. Images of one subject ("010_HC" and "010_2HC") share a group
and never cross splits: 70/15/15 by group with a seed. The pixel size and reference circumference stay on every row,
so measurements are evaluated in millimetres against the publisher's reference.

    python scripts/register_hc18_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
import zipfile
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from ml_training import hc18_measure  # noqa: E402
BASE = Path("C:/MedTwin_Datasets/HC18")
DATASET_ID = "hc18-fetal-head"
TASK_ID = "hc18-fetal-head-segmentation"
SEED = 20261024


def main() -> int:
    archive = BASE / "training_set.zip"
    receipt = json.loads((BASE / "training_set.zip.receipt.json").read_text(encoding="utf-8"))
    if not (BASE / "training_set").exists():
        with zipfile.ZipFile(archive) as handle:
            if any(name.startswith(("/", "\\")) or ".." in Path(name).parts for name in handle.namelist()):
                raise SystemExit("unsafe archive member")
            handle.extractall(BASE)
    reference = {row["filename"]: row for row in csv.DictReader(open(BASE / "training_set_pixel_size_and_HC.csv", encoding="utf-8"))}
    masks = BASE / "filled_masks"
    masks.mkdir(exist_ok=True)
    rows, floor = [], []
    images = sorted(path for path in (BASE / "training_set").glob("*HC.png"))  # includes second images such as 010_2HC.png
    if len(images) != len(reference):
        raise SystemExit(f"{len(images)} images but {len(reference)} reference rows")
    for image in images:
        outline = np.asarray(Image.open(image.with_name(image.stem + "_Annotation.png")).convert("L")) > 127
        # The sonographer's annotation is an ellipse: fit it (border pixels excluded) and fill the fitted ellipse.
        ys, xs = np.nonzero(outline)
        inside = (xs > 0) & (ys > 0) & (xs < outline.shape[1] - 1) & (ys < outline.shape[0] - 1)
        ellipse = hc18_measure.fit_ellipse(np.stack([xs[inside], ys[inside]], axis=1))
        filled = hc18_measure.filled_mask(outline.shape, ellipse)
        target = masks / image.name
        Image.fromarray((filled * 255).astype(np.uint8)).save(target)
        info = reference[image.name]
        floor.append(abs(hc18_measure.circumference_mm(ellipse, float(info["pixel size(mm)"])) - float(info["head circumference (mm)"])))
        rows.append({"entry": f"training_set/{image.name}", "path": str(image.resolve()), "mask_file": str(target.resolve()),
                     "image_id": image.stem, "group_id": "subject-" + re.match(r"^(\d+)", image.name).group(1),
                     "pixel_size_mm": info["pixel size(mm)"], "head_circumference_mm": info["head circumference (mm)"]})
    groups = sorted({row["group_id"] for row in rows})
    random.Random(SEED).shuffle(groups)
    cut1, cut2 = int(0.70 * len(groups)), int(0.85 * len(groups))
    part = {group: ("train" if i < cut1 else "val" if i < cut2 else "test") for i, group in enumerate(groups)}
    for row in rows:
        row["split"] = part[row["group_id"]]
    fields = ["entry", "path", "mask_file", "image_id", "split", "group_id", "pixel_size_mm", "head_circumference_mm"]
    manifest = ROOT / "_derived" / "datasets" / TASK_ID / "samples.csv"
    manifest.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with manifest.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
            digest.update(f"{row['entry']}\t{row['split']}\t{row['group_id']}\n".encode("utf-8"))
    counts = {split: sum(row["split"] == split for row in rows) for split in ("train", "val", "test")}
    preparation = {"samples": len(rows), "per_split": counts, "groups": len(groups), "sample_manifest": str(manifest),
                   "dataset_version": digest.hexdigest(), "split_method": f"subject groups (image-name number) 70/15/15, seed {SEED}",
                   "measurement_reference": "publisher head circumference (mm) and pixel size (mm) per image",
                   # Method floor: the ellipse fit + Ramanujan measurement applied to the sonographer's own outline.
                   "measurement_method_floor_mm": {"mean_absolute_error": float(np.mean(floor)), "p95_absolute_error": float(np.percentile(floor, 95)),
                                                   "max_absolute_error": float(np.max(floor))}}
    record = {
        "id": DATASET_ID, "archive": archive.name, "title": "HC18 fetal head circumference (2-D ultrasound)", "modality": "ULTRASOUND",
        "system": "pregnancy", "identity": "999 annotated fetal head ultrasound images (Radboud University Medical Center)", "labels": "OUTLINE_PNG_AND_HC_TABLE",
        "official_splits": False, "patient_ids": "SUBJECT_NUMBER_IN_FILE_NAME", "source_archive": receipt["source_url"], "source_sha256": receipt["sha256"],
        "files": len(rows), "location": str(BASE).replace("\\", "/"),
        "license": {"status": "VERIFIED", "name": "CC BY 4.0", "source": receipt["licence_evidence"]["page"], "verified_on": receipt["downloaded_at"][:10],
                    "evidence": {"page_sha256": receipt["licence_evidence"]["page_sha256"]},
                    "citation": "van den Heuvel TLA, de Bruijn D, de Korte CL, van Ginneken B. Automated measurement of fetal head circumference using 2D ultrasound images. PLoS ONE 13(8):e0200412 (2018).",
                    "authorization_status": "VERIFIED", "authorization_scope": "NON_COMMERCIAL_RESEARCH_UNDER_RECORDED_TERMS",
                    "authorized_by": "project owner (chat instruction)", "authorized_on": "2026-11-14",
                    "authorization_reason": "Owner approved the download and research training on 2026-11-14; CC BY 4.0 on the Zenodo record."},
        "privacy": "PUBLISHER_DE_IDENTIFIED", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": TASK_ID, "type": "SEGMENTATION", "target": "fetal head (filled sonographer ellipse)", "class_name": "fetal_head",
                   "flags": ["TASK_SUPPORTED_BY_LABELS"], "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING",
                   "preparation": preparation}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw[:4096] else "\n"
    registry = json.loads(raw.decode("utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != DATASET_ID] + [record]
    path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").replace("\n", newline).encode("utf-8"))
    print(json.dumps({"samples": len(rows), "groups": len(groups), "per_split": counts, "method_floor_mm": preparation["measurement_method_floor_mm"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
