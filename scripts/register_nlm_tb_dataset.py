"""Register the NLM tuberculosis chest radiograph sets (Shenzhen, Montgomery County) for training.

Source: data.lhncbc.nlm.nih.gov/public/Tuberculosis-Chest-X-ray-Datasets (mirrored with MD5 checks by the download
script; the Open-i archive links were down for maintenance on 2026-11-06). Labels come from the publisher's file names
(..._0.png normal, ..._1.png tuberculosis manifestation). Each file is one case. Images are grouped by perceptual hash
(dHash, Hamming distance <= 4) so near-duplicates never cross splits; groups are split 70/15/15 with a seed,
stratified by site and label. The terms (research group use only, no redistribution, citations) are the publisher's
read-me files, quoted in the record.

    python scripts/register_nlm_tb_dataset.py --root D:/project/MedTwin_Datasets/Tuberculosis/NLM_data_server
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
DATASET_ID = "nlm-tb-cxr"
TASK_ID = "nlm-tb-cxr-classification"
SEED = 20261024
FRACTIONS = {"train": 0.70, "val": 0.15, "test": 0.15}
DHASH_DISTANCE = 4
SITES = {"shenzhen": ("Shenzhen-Hospital-CXR-Set/CXR_png", "CHNCXR"), "montgomery": ("Montgomery-County-CXR-Set/MontgomerySet/CXR_png", "MCUCXR")}
NAME = re.compile(r"^(CHNCXR|MCUCXR)_(\d{4})_([01])\.png$")


THUMBNAIL = 64
# Mean absolute grey-level difference of 64 x 64 thumbnails below which two radiographs are the same image
# (re-exports, rescaled copies). Chest radiographs all look alike at a 9 x 8 hash, so the hash alone would chain
# different patients into one group; every link must also pass this check.
NEAR_COPY_MAD = 3.0


def fingerprint(path: Path) -> tuple[int, np.ndarray]:
    with Image.open(path) as image:
        grey = image.convert("L")
        small = np.asarray(grey.resize((9, 8), Image.Resampling.LANCZOS), dtype=np.int16)
        thumb = np.asarray(grey.resize((THUMBNAIL, THUMBNAIL), Image.Resampling.LANCZOS), dtype=np.float32)
    bits = (small[:, 1:] > small[:, :-1]).ravel()
    return int("".join("1" if bit else "0" for bit in bits), 2), thumb


def groups_by_hash(hashes: list[int], thumbs: list[np.ndarray]) -> list[int]:
    parent = list(range(len(hashes)))

    def find(item: int) -> int:
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for i in range(len(hashes)):
        for j in range(i + 1, len(hashes)):
            if bin(hashes[i] ^ hashes[j]).count("1") <= DHASH_DISTANCE and float(np.abs(thumbs[i] - thumbs[j]).mean()) <= NEAR_COPY_MAD:
                parent[find(i)] = find(j)
    return [find(i) for i in range(len(hashes))]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--root", type=Path, required=True)
    args = parser.parse_args()
    samples = []
    for site, (folder, prefix) in SITES.items():
        for path in sorted((args.root / folder).glob(f"{prefix}_*.png")):
            match = NAME.match(path.name)
            if not match:
                raise SystemExit(f"unexpected file name {path.name}")
            samples.append({"entry": f"{site}/{path.name}", "path": str(path.resolve()), "site": site, "case": f"{site}-{match.group(2)}",
                            "label": "tuberculosis" if match.group(3) == "1" else "normal"})
    if len(samples) < 790:
        raise SystemExit(f"only {len(samples)} radiographs found; the download is incomplete (Shenzhen 662 + Montgomery 138 expected)")
    prints = [fingerprint(Path(sample["path"])) for sample in samples]
    hashes = [value for value, _ in prints]
    groups = groups_by_hash(hashes, [thumb for _, thumb in prints])
    for sample, group, value in zip(samples, groups, hashes):
        sample["group_id"] = f"g{group:04d}"
        sample["dhash"] = f"{value:016x}"
    members: dict[str, list[int]] = defaultdict(list)
    for index, sample in enumerate(samples):
        members[sample["group_id"]].append(index)
    strata: dict[str, list[str]] = defaultdict(list)
    for group, indices in members.items():
        key = Counter(f"{samples[i]['site']}:{samples[i]['label']}" for i in indices).most_common(1)[0][0]
        strata[key].append(group)
    rng = random.Random(SEED)
    for key in sorted(strata):
        group_ids = sorted(strata[key])
        rng.shuffle(group_ids)
        total = sum(len(members[g]) for g in group_ids)
        assigned = {"train": 0, "val": 0}
        for group in group_ids:
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
    fields = ["entry", "path", "label", "split", "group_id", "site", "case", "dhash"]
    target = ROOT / "_derived" / "datasets" / TASK_ID / "samples.csv"
    target.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for sample in sorted(samples, key=lambda item: item["entry"]):
            writer.writerow({field: sample[field] for field in fields})
            digest.update(("\t".join(str(sample[field]) for field in ("entry", "label", "split", "group_id")) + "\n").encode("utf-8"))
    counts = Counter((sample["split"], sample["label"]) for sample in samples)
    labels = sorted({sample["label"] for sample in samples})
    group_sizes = Counter(sample["group_id"] for sample in samples)
    preparation = {
        "samples": len(samples), "labels": labels, "per_split": {split: sum(counts[(split, label)] for label in labels) for split in FRACTIONS},
        "per_split_per_label": {split: {label: counts[(split, label)] for label in labels} for split in FRACTIONS},
        "per_site": dict(Counter(sample["site"] for sample in samples)),
        "near_duplicate_groups_with_more_than_one_image": sum(1 for size in group_sizes.values() if size > 1),
        "near_duplicate_groups_with_conflicting_labels": sum(1 for group, size in group_sizes.items()
                                                              if size > 1 and len({samples[i]["label"] for i in members[group]}) > 1),
        "split_method": (f"near-copy groups (dHash distance <= {DHASH_DISTANCE} and mean thumbnail difference <= {NEAR_COPY_MAD} grey levels) "
                         f"split 70/15/15, stratified by site and label, seed {SEED}"),
        "largest_group": max(group_sizes.values()),
        "group_unit": "near-duplicate group (each file is one case)", "minimum_samples_per_class": 50, "classes_below_minimum": [],
        "sample_manifest": str(target), "dataset_version": digest.hexdigest(),
    }
    citation = ("Jaeger S, Karargyris A, Candemir S, et al. Automatic tuberculosis screening using chest radiographs. IEEE Trans Med Imaging "
                "33(2):233-45 (2014); Candemir S, Jaeger S, Palaniappan K, et al. Lung segmentation in chest radiographs using anatomical atlases "
                "with nonrigid registration. IEEE Trans Med Imaging 33(2):577-90 (2014). Source: National Library of Medicine, NIH, Bethesda, MD, "
                "USA; Shenzhen No.3 People's Hospital, Guangdong Medical College, Shenzhen, China; Department of Health and Human Services, "
                "Montgomery County, MD, USA.")
    record = {
        "id": DATASET_ID, "archive": "data.lhncbc.nlm.nih.gov mirror", "title": "NLM tuberculosis chest radiographs (Shenzhen and Montgomery County sets)",
        "modality": "XRAY", "system": "lungs", "identity": f"{preparation['per_site']} frontal chest radiographs; labels from the publisher's file names",
        "labels": "FILE_NAME_SUFFIX", "official_splits": False, "patient_ids": "ONE_CASE_PER_FILE",
        "source_archive": "https://data.lhncbc.nlm.nih.gov/public/Tuberculosis-Chest-X-ray-Datasets/ (per-file MD5 = listing ETag)",
        "files": len(samples), "location": str(args.root.resolve()).replace("\\", "/"),
        "license": {
            "status": "PUBLISHER_TERMS_IN_README", "authorization_status": "VERIFIED",
            "authorization_reason": ("NLM-ChinaCXRSet-ReadMe.docx and NLM-MontgomeryCXRSet-ReadMe.pdf: the sets are de-identified and publicly released by "
                                     "the NLM for research; users must not share them outside their research group and must cite the publications. "
                                     "The repository owner approved the download on 2026-11-06."),
            "authorized_by": "publisher read-me terms; download approved by the repository owner on 2026-11-06", "authorized_on": "2026-11-06",
            "authorization_scope": "local research training and evaluation; images are not committed, shared or redistributed",
            "name": "NLM public research release (no redistribution outside the research group; citation required)",
            "source": "read-me files in the NLM folders", "verified_on": "2026-11-06", "citation": citation,
        },
        "privacy": "PUBLISHER_DE_IDENTIFIED", "exact_duplicate_overlap": {}, "notes": [],
        "tasks": [{"task_id": TASK_ID, "type": "CLASSIFICATION", "target": "tuberculosis manifestation vs normal on a frontal chest radiograph",
                   "flags": ["TASK_SUPPORTED_BY_LABELS"], "training_eligible": True, "validation_ready": True, "readiness": "READY_FOR_TRAINING",
                   "minimum_samples_per_class": 50, "preparation": preparation}],
    }
    path = ROOT / "dataset_registry" / "tasks.json"
    registry = json.loads(path.read_text(encoding="utf-8"))
    registry["datasets"] = [item for item in registry["datasets"] if item["id"] != DATASET_ID] + [record]
    path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: preparation[key] for key in ("samples", "per_split_per_label", "per_site", "near_duplicate_groups_with_more_than_one_image",
                                                        "near_duplicate_groups_with_conflicting_labels")}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
