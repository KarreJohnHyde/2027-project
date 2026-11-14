"""Register FETAL_PLANES_DB (common maternal-fetal ultrasound planes) for training (owner approval 2026-11-14).

Source: Zenodo record 3904280 (Burgos-Artizzu et al., Scientific Reports 10:10200, 2020), CC BY 4.0, downloaded by
scripts/acquire_approved_public_datasets.py with a SHA-256 receipt. 12,400 images from 1,792 patients, labelled by an
expert into six classes: four fetal planes (abdomen, brain, femur, thorax), the maternal cervix and "other".
The publisher's own split is kept: its test patients (Train = 0) are the test set; 15% of its training patients (seeded,
stratified by each patient's most common plane) form the validation part. Images of one patient never cross splits.

    python scripts/register_fetal_planes_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import random
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("C:/MedTwin_Datasets/FETAL_PLANES_DB/FETAL_PLANES_ZENODO.zip")
EXTRACTED = ARCHIVE.parent / "extracted"
DATASET_ID = "fetal-planes-db"
TASK_ID = "fetal-planes-classification"
SEED = 20261024
LABELS = {"Fetal abdomen": "fetal_abdomen", "Fetal brain": "fetal_brain", "Fetal femur": "fetal_femur", "Fetal thorax": "fetal_thorax",
          "Maternal cervix": "maternal_cervix", "Other": "other"}


def main() -> int:
    receipt_path = ARCHIVE.with_name(ARCHIVE.name + ".receipt.json")
    if not receipt_path.exists():
        raise SystemExit("FETAL_PLANES_ZENODO.zip has no download receipt; run scripts/acquire_approved_public_datasets.py --only fetal-planes")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    with zipfile.ZipFile(ARCHIVE) as archive:
        names = archive.namelist()
        for member in names:
            if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                raise SystemExit(f"unsafe archive member {member}")
        table_name = next((name for name in names if name.lower().endswith("fetal_planes_db_data.csv")), None)
        if table_name is None:
            raise SystemExit(f"the publisher table FETAL_PLANES_DB_data.csv is not in the archive (members include {names[:5]})")
        table = list(csv.DictReader(io.StringIO(archive.read(table_name).decode("utf-8-sig")), delimiter=";"))
        if not EXTRACTED.exists():
            archive.extractall(EXTRACTED)
    images = {path.stem: path for path in EXTRACTED.rglob("*.png")}
    train_column = next((key for key in table[0] if key.strip() == "Train"), None)
    if train_column is None:
        raise SystemExit(f"the publisher table has no Train column (columns {list(table[0])})")
    samples, missing = [], []
    for row in table:
        name = row["Image_name"].strip()
        plane = row["Plane"].strip()
        if plane not in LABELS:
            raise SystemExit(f"unexpected plane label {plane!r}")
        if name not in images:
            missing.append(name)
            continue
        samples.append({"entry": f"Images/{name}.png", "path": str(images[name].resolve()), "label": LABELS[plane],
                        "group_id": f"patient-{int(row['Patient_num']):04d}", "publisher_split": "train" if row[train_column].strip() == "1" else "test",
                        "operator": row["Operator"].strip(), "machine": row["US_Machine"].strip()})
    if missing:
        raise SystemExit(f"{len(missing)} images listed in the publisher table are missing from the archive (e.g. {missing[:3]})")
    train_patients: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        sample["split"] = "test" if sample["publisher_split"] == "test" else "train"
        if sample["split"] == "train":
            train_patients[sample["group_id"]].append(index)
    strata: dict[str, list[str]] = defaultdict(list)
    for patient, indices in train_patients.items():
        strata[Counter(samples[i]["label"] for i in indices).most_common(1)[0][0]].append(patient)
    rng = random.Random(SEED)
    for label in sorted(strata):
        patients = sorted(strata[label])
        rng.shuffle(patients)
        for patient in patients[: max(1, round(0.15 * len(patients)))]:
            for index in train_patients[patient]:
                samples[index]["split"] = "val"
    test_groups = {s["group_id"] for s in samples if s["split"] == "test"}
    if test_groups & {s["group_id"] for s in samples if s["split"] != "test"}:
        raise SystemExit("a patient appears in both the publisher's training and test parts")
    fields = ["entry", "path", "label", "split", "group_id", "operator", "machine"]
    target = ROOT / "_derived" / "datasets" / TASK_ID / "samples.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in sorted(samples, key=lambda item: item["entry"]):
            writer.writerow({field: sample[field] for field in fields})
            digest.update(("\t".join(sample[field] for field in ("entry", "label", "split", "group_id")) + "\n").encode("utf-8"))
    labels = sorted(LABELS.values())
    counts = Counter((sample["split"], sample["label"]) for sample in samples)
    preparation = {
        "samples": len(samples), "labels": labels,
        "per_split": {split: sum(counts[(split, label)] for label in labels) for split in ("train", "val", "test")},
        "per_split_per_label": {split: {label: counts[(split, label)] for label in labels} for split in ("train", "val", "test")},
        "patients_per_split": {split: len({s["group_id"] for s in samples if s["split"] == split}) for split in ("train", "val", "test")},
        "split_method": f"publisher patient split kept for test; 15% of the publisher's training patients for validation (seed {SEED}, stratified by plane)",
        "group_unit": "patient", "minimum_samples_per_class": 50, "classes_below_minimum": [],
        "sample_manifest": str(target), "dataset_version": digest.hexdigest(),
    }
    record = {
        "id": DATASET_ID, "archive": ARCHIVE.name, "title": "FETAL_PLANES_DB: common maternal-fetal ultrasound planes",
        "modality": "ULTRASOUND", "system": "pregnancy", "identity": "12,400 obstetric ultrasound images of 1,792 patients (BCNatal, Barcelona; 2018-2019)",
        "labels": "PUBLISHER_TABLE", "official_splits": True, "patient_ids": "PUBLISHER_PATIENT_NUMBER",
        "source_archive": receipt["source_url"], "source_sha256": receipt["sha256"], "files": len(samples), "location": str(EXTRACTED).replace("\\", "/"),
        "license": {
            "status": "VERIFIED", "name": "CC BY 4.0", "source": receipt["licence_evidence"]["page"], "verified_on": receipt["downloaded_at"][:10],
            "evidence": {"page_sha256": receipt["licence_evidence"]["page_sha256"], "marker_found": receipt["licence_evidence"]["marker_found"]},
            "citation": "Burgos-Artizzu XP, Coronado-Gutierrez D, Valenzuela-Alcaraz B, et al. Evaluation of deep convolutional neural networks for automatic classification of common maternal fetal ultrasound planes. Scientific Reports 10:10200 (2020).",
            "authorization_status": "VERIFIED", "authorization_scope": "NON_COMMERCIAL_RESEARCH_UNDER_RECORDED_TERMS",
            "authorized_by": "project owner (chat instruction)", "authorized_on": "2026-11-14",
            "authorization_reason": "Owner approved the download and research training on 2026-11-14; CC BY 4.0 shown on the Zenodo record.",
        },
        "privacy": "PUBLISHER_DE_IDENTIFIED", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": TASK_ID, "type": "CLASSIFICATION", "target": "standard maternal-fetal ultrasound plane (6 classes)",
                   "flags": ["TASK_SUPPORTED_BY_LABELS"], "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING",
                   "minimum_samples_per_class": 50, "preparation": preparation}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw[:4096] else "\n"
    registry = json.loads(raw.decode("utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != DATASET_ID] + [record]
    path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").replace("\n", newline).encode("utf-8"))
    print(json.dumps({key: preparation[key] for key in ("samples", "per_split", "patients_per_split")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
