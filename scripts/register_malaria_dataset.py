"""Register the NIH/NLM malaria thin-smear cell images for training (owner approval 2026-11-14).

Source: data.lhncbc.nlm.nih.gov/public/Malaria/cell_images.zip, downloaded by scripts/acquire_approved_public_datasets.py
with a SHA-256 receipt. 27,558 segmented red-blood-cell crops, labelled Parasitized or Uninfected by the publisher
(Rajaraman et al., PeerJ 2018). File names begin with the slide code; "C<slide>P<patient>" for patients with malaria and
"C<n>" for the healthy patients. Cells of one patient never cross splits: groups are patients, split 70/15/15 with a
seed, stratified by each patient's majority label. Uninfected cells of infected patients stay with that patient.

    python scripts/register_malaria_dataset.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import random
import re
import sys
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("C:/MedTwin_Datasets/NIH_Malaria/cell_images.zip")
EXTRACTED = ARCHIVE.parent
DATASET_ID = "nih-malaria-cell-images"
TASK_ID = "nih-malaria-cell-classification"
SEED = 20261024
FRACTIONS = {"train": 0.70, "val": 0.15, "test": 0.15}
PREFIX = re.compile(r"^C(\d+)(?:P(\d+))?")


def patient(name: str) -> str:
    match = PREFIX.match(name)
    if not match:
        raise SystemExit(f"unexpected file name {name}")
    return f"P{match.group(2)}" if match.group(2) else f"H{match.group(1)}"


def main() -> int:
    receipt_path = ARCHIVE.with_name(ARCHIVE.name + ".receipt.json")
    if not receipt_path.exists():
        raise SystemExit("cell_images.zip has no download receipt; run scripts/acquire_approved_public_datasets.py --only malaria")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    root = EXTRACTED / "cell_images"
    if not root.exists():
        with zipfile.ZipFile(ARCHIVE) as archive:
            for member in archive.namelist():
                if member.startswith(("/", "\\")) or ".." in Path(member).parts:
                    raise SystemExit(f"unsafe archive member {member}")
            archive.extractall(EXTRACTED)
    samples = []
    for label_folder, label in (("Parasitized", "parasitized"), ("Uninfected", "uninfected")):
        for path in sorted((root / label_folder).glob("*.png")):
            samples.append({"entry": f"{label_folder}/{path.name}", "path": str(path.resolve()), "label": label, "group_id": patient(path.name)})
    if len(samples) != 27558:
        raise SystemExit(f"{len(samples)} cell images found; the publisher's archive holds 27,558")
    members: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        members[sample["group_id"]].append(index)
    strata: dict[str, list[str]] = defaultdict(list)
    for group, indices in members.items():
        strata[Counter(samples[i]["label"] for i in indices).most_common(1)[0][0]].append(group)
    rng = random.Random(SEED)
    for key in sorted(strata):
        groups = sorted(strata[key])
        rng.shuffle(groups)
        total = sum(len(members[g]) for g in groups)
        assigned = {"train": 0, "val": 0}
        for group in groups:
            size = len(members[group])
            if assigned["train"] + size <= FRACTIONS["train"] * total or assigned["train"] == 0:
                split = "train"
            elif assigned["val"] + size <= FRACTIONS["val"] * total or assigned["val"] == 0:
                split = "val"
            else:
                split = "test"
            if split in assigned:
                assigned[split] += size
            for index in members[group]:
                samples[index]["split"] = split
    fields = ["entry", "path", "label", "split", "group_id"]
    target = ROOT / "_derived" / "datasets" / TASK_ID / "samples.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in sorted(samples, key=lambda item: item["entry"]):
            writer.writerow({field: sample[field] for field in fields})
            digest.update(("\t".join(sample[field] for field in ("entry", "label", "split", "group_id")) + "\n").encode("utf-8"))
    counts = Counter((sample["split"], sample["label"]) for sample in samples)
    labels = ["parasitized", "uninfected"]
    patients = {split: len({s["group_id"] for s in samples if s["split"] == split}) for split in FRACTIONS}
    preparation = {
        "samples": len(samples), "labels": labels, "per_split": {split: sum(counts[(split, label)] for label in labels) for split in FRACTIONS},
        "per_split_per_label": {split: {label: counts[(split, label)] for label in labels} for split in FRACTIONS}, "patients_per_split": patients,
        "split_method": f"patients (slide code prefix) split 70/15/15, stratified by each patient's majority label, seed {SEED}",
        "group_unit": "patient", "minimum_samples_per_class": 50, "classes_below_minimum": [],
        "sample_manifest": str(target), "dataset_version": digest.hexdigest(),
    }
    record = {
        "id": DATASET_ID, "archive": ARCHIVE.name, "title": "NIH/NLM malaria thin blood smear cell images",
        "modality": "MICROSCOPY", "system": "blood", "identity": "27,558 segmented red blood cell crops from Giemsa-stained thin smears (Chittagong Medical College Hospital, Bangladesh)",
        "labels": "PUBLISHER_FOLDERS", "official_splits": False, "patient_ids": "SLIDE_CODE_IN_FILE_NAME",
        "source_archive": receipt["source_url"], "source_sha256": receipt["sha256"], "files": len(samples), "location": str(root).replace("\\", "/"),
        "license": {
            "status": "VERIFIED", "name": receipt["licence"], "source": receipt["licence_evidence"]["page"], "verified_on": receipt["downloaded_at"][:10],
            "evidence": {"page_sha256": receipt["licence_evidence"]["page_sha256"]},
            "citation": "Rajaraman S, Antani SK, Poostchi M, et al. Pre-trained convolutional neural networks as feature extractors toward improved malaria parasite detection in thin blood smear images. PeerJ 6:e4568 (2018).",
            "authorization_status": "VERIFIED", "authorization_scope": "NON_COMMERCIAL_RESEARCH_UNDER_RECORDED_TERMS",
            "authorized_by": "project owner (chat instruction)", "authorized_on": "2026-11-14",
            "authorization_reason": "Owner approved the download and research training on 2026-11-14; NLM public research release.",
        },
        "privacy": "PUBLISHER_DE_IDENTIFIED", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": TASK_ID, "type": "CLASSIFICATION", "target": "parasitized vs uninfected red blood cell",
                   "flags": ["TASK_SUPPORTED_BY_LABELS"], "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING",
                   "minimum_samples_per_class": 50, "preparation": preparation}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    raw = path.read_bytes()
    newline = "\r\n" if b"\r\n" in raw[:4096] else "\n"
    registry = json.loads(raw.decode("utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != DATASET_ID] + [record]
    path.write_bytes((json.dumps(registry, indent=2, ensure_ascii=False) + "\n").replace("\n", newline).encode("utf-8"))
    print(json.dumps({key: preparation[key] for key in ("samples", "per_split_per_label", "patients_per_split")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
