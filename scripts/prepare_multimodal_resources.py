"""Validate joins and write research manifests for the reviewed multimodal downloads.

Preserves original labels/metadata. Does not train, activate or validate a clinical model.
"""
from __future__ import annotations

import csv
import hashlib
import json
import shutil
import stat
import zipfile
from collections import Counter, defaultdict
from pathlib import Path

from acquire_public_datasets import ROOT, digest, write_json

DATA = Path("C:/MedTwin_Datasets")
OUT = ROOT / "_derived/datasets/multimodal"
RESERVE = 60 * 1024**3
FEATURES = ("age", "gender", "region", "fitspatrick", "fitzpatrick", "diameter_1", "diameter_2", "itch", "grew", "hurt",
            "changed", "bleed", "elevation", "smoke", "drink", "background_father", "background_mother", "cancer_history",
            "skin_cancer_history", "pesticide", "has_piped_water", "has_sewage_system")


def extract_safe(archive: Path, root: Path, max_bytes=15 * 1024**3):
    """Bound expanded bytes and reject absolute paths, traversal and link members."""
    root.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as bundle:
        entries = bundle.infolist()
        total = sum(item.file_size for item in entries)
        if total > max_bytes:
            raise ValueError("Expanded archive exceeds the reviewed size budget")
        pending = sum(item.file_size for item in entries if not item.is_dir() and not (root / item.filename).exists())
        if shutil.disk_usage(root).free < RESERVE + pending:
            raise OSError("Not enough extraction space above the dataset reserve")
        targets = []
        for item in entries:
            name = item.filename.replace("\\", "/")
            parts = name.split("/")
            if name.startswith("/") or any(part in ("..", ".") or ":" in part for part in parts):
                raise ValueError(f"Unsafe archive member: {item.filename}")
            if stat.S_ISLNK(item.external_attr >> 16):
                raise ValueError("Archive links are not permitted")
            target = (root / name).resolve()
            target.relative_to(root.resolve())
            targets.append((item, target))
        for item, target in targets:
            if item.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue
            if target.exists():
                import zlib
                crc = 0
                with target.open("rb") as handle:
                    for block in iter(lambda: handle.read(1024**2), b""):
                        crc = zlib.crc32(block, crc)
                if target.stat().st_size != item.file_size or crc != item.CRC:
                    raise ValueError(f"Existing extraction differs: {target.name}")
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            part = target.with_name(target.name + ".extracting")
            with bundle.open(item) as source, part.open("wb") as destination:
                shutil.copyfileobj(source, destination, 1024**2)
            if part.stat().st_size != item.file_size:
                raise ValueError("Incomplete ZIP extraction")
            part.replace(target)


def split_group(key):
    value = int(hashlib.sha256(("medtwin-fusion-20261107:" + key).encode()).hexdigest()[:8], 16) % 100
    return "train" if value < 70 else "val" if value < 85 else "test"


def jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for row in rows:
            handle.write(json.dumps(row, ensure_ascii=True) + "\n")


def prepare_pad(root=DATA / "PAD_UFES20", output=OUT / "pad-ufes-20"):
    source = root / "extracted"
    extract_safe(root / "pad-ufes20-v1.zip", source)
    metadata = None
    rows = None
    for path in sorted(source.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            if {"img_id", "patient_id", "diagnostic"}.issubset(reader.fieldnames or []):
                metadata, rows = path, list(reader)
                break
    if metadata is None or len(rows) != 2298:
        raise ValueError("PAD-UFES-20 metadata is absent or differs from the original 2,298 rows")
    images = {}
    for path in source.rglob("*"):
        if path.suffix.lower() not in (".png", ".jpg", ".jpeg"):
            continue
        if path.name in images:
            raise ValueError("Duplicate image names need explicit reconciliation")
        images[path.name] = path
    # Merge patient groups when identical image content appears under different IDs.
    parent = {}
    def find(key):
        parent.setdefault(key, key)
        if parent[key] != key:
            parent[key] = find(parent[key])
        return parent[key]
    def union(a, b):
        a, b = find(a), find(b)
        parent[max(a, b)] = min(a, b)
    by_hash = {}
    joined = []
    for row in rows:
        image = images.get(row["img_id"])
        if image is None or not row["patient_id"] or not row["diagnostic"]:
            raise ValueError("Missing image, patient grouping ID or original diagnosis")
        checksum = digest(image)
        patient = str(row["patient_id"])
        find(patient)
        if checksum in by_hash:
            union(patient, by_hash[checksum])
        by_hash[checksum] = patient
        joined.append({"image_path": str(image.resolve()), "image_sha256": checksum, "patient_id": patient,
                       "lesion_id": row.get("lesion_id"), "label": row["diagnostic"],
                       "features": {key: row.get(key) for key in FEATURES if key in row}})
    for row in joined:
        row["split"] = split_group(find(row["patient_id"]))
    jsonl(output / "samples.jsonl", joined)
    counts = {split: dict(Counter(row["label"] for row in joined if row["split"] == split)) for split in ("train", "val", "test")}
    summary = {"dataset": "PAD-UFES-20", "rows": len(joined), "patients": len({r["patient_id"] for r in joined}),
               "source_metadata": str(metadata), "metadata_sha256": digest(metadata), "licence": "CC BY 4.0",
               "split": "deterministic 70/15/15 approximate allocation over patient groups merged by exact image hashes",
               "per_split_per_class": counts, "features": [key for key in FEATURES if key in rows[0]],
               "excluded_from_features": ["diagnostic", "biopsed", "biopsied", "patient_id", "lesion_id", "img_id"],
               "status": "PAIRED_RESEARCH_MANIFEST_PREPARED", "trainer_status": "Image/tabular fusion adapter and experiment protocol still required; no model trained or registered."}
    write_json(output / "preparation.json", summary)
    return summary


def prepare_vqa(root=DATA / "VQA_RAD", output=OUT / "vqa-rad"):
    rows = json.loads((root / "VQA_RAD Dataset Public.json").read_text(encoding="utf-8-sig"))
    prepared = []
    images = {}
    for row in rows:
        name = row["image_name"]
        path = (root / "images" / name).resolve()
        path.relative_to((root / "images").resolve())
        if not path.is_file():
            raise ValueError("VQA-RAD question references a missing image")
        if name not in images:
            images[name] = digest(path)
        checksum = images[name]
        prepared.append({"image_path": str(path), "image_sha256": checksum, "question": row["question"],
                         "answer": row["answer"], "split": split_group(checksum), "question_type": row.get("question_type"),
                         "answer_type": row.get("answer_type")})
    jsonl(output / "samples.jsonl", prepared)
    summary = {"dataset": "VQA-RAD", "qa_rows": len(prepared), "referenced_images": len(images), "licence": "CC0 1.0 Universal",
               "per_split_qa": dict(Counter(r["split"] for r in prepared)),
               "split": "grouped by exact image SHA-256; all questions for identical images remain in the same split",
               "status": "PAIRED_RESEARCH_MANIFEST_PREPARED", "limitations": "No patient IDs, clinical outcome linkage, lesion masks or true 3D geometry; image grouping does not establish patient independence."}
    write_json(output / "preparation.json", summary)
    return summary


def prepare_cbis(root=DATA / "CBIS_DDSM", output=OUT / "cbis-ddsm"):
    source = root / "extracted"
    extract_safe(root / "cbis-ddsm-v1.zip", source)
    return audit_cbis_tables(source, output)


def cbis_patient_split(rows):
    """Keep every publisher-test patient held out, including their training-table rows."""
    test_patients = {row["patient_id"] for row in rows if row["publisher_split"] == "test"}
    result = []
    for row in rows:
        if row["patient_id"] in test_patients:
            split = "test"
        else:
            value = int(hashlib.sha256(("medtwin-cbis-20261107:" + row["patient_id"]).encode()).hexdigest()[:8], 16) % 100
            split = "train" if value < 85 else "val"
        result.append({**row, "split": split})
    return result


def audit_cbis_tables(source, output=OUT / "cbis-ddsm"):
    tables = []
    patient_splits = defaultdict(set)
    cases = []
    for path in sorted(source.rglob("*.csv")):
        with path.open(encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            fields = reader.fieldnames or []
            rows = list(reader)
        tables.append({"path": str(path), "sha256": digest(path), "rows": len(rows), "columns": fields})
        if "patient_id" in fields and "case_description" in path.name:
            split = "test" if "test" in path.name.lower() else "train" if "train" in path.name.lower() else "unknown"
            for index, row in enumerate(rows, 1):
                patient_splits[row["patient_id"]].add(split)
                cases.append({"patient_id": row["patient_id"], "publisher_split": split, "source_table": str(path), "source_row": index,
                              "pathology": row.get("pathology"), "abnormality_type": row.get("abnormality type"),
                              "original_dicom_image_path": row.get("image file path"), "original_roi_mask_path": row.get("ROI mask file path")})
    if len(tables) < 4:
        raise ValueError("Expected CBIS-DDSM clinical/annotation CSV tables")
    cases = cbis_patient_split(cases)
    jsonl(output / "case_metadata.jsonl", cases)
    grouped = defaultdict(set)
    for case in cases:
        grouped[case["patient_id"]].add(case["split"])
    if any(len(splits) != 1 for splits in grouped.values()):
        raise ValueError("Derived CBIS-DDSM patient split is inconsistent")
    summary = {"dataset": "CBIS-DDSM Kaggle JPEG conversion", "tables": tables,
               "jpeg_files": sum(1 for p in source.rglob("*") if p.suffix.lower() in (".jpg", ".jpeg")),
               "patients_in_multiple_publisher_splits": sum(len(v) > 1 for v in patient_splits.values()),
               "derived_metadata_cases": len(cases), "derived_split_cases": dict(Counter(row["split"] for row in cases)),
               "derived_patient_cross_split_overlap": 0,
               "derived_split_rule": "All rows for any publisher-test patient are held out; remaining patients allocated approximately 85/15 train/validation by deterministic patient hash. Original CSVs unchanged.",
               "status": "EXTRACTED_NEEDS_COORDINATE_AND_JOIN_AUDIT",
               "licence": "CC BY-SA 3.0 for this Kaggle distribution; retain original TCIA attribution and terms",
               "limitations": "Full-image, crop and ROI paths need explicit correspondence/coordinate verification. Original CSVs are preserved; no boxes were invented and no detector or fusion model was trained."}
    write_json(output / "preparation.json", summary)
    return summary


def main():
    summaries = [prepare_vqa(), prepare_pad(), prepare_cbis()]
    write_json(OUT / "preparation.json", summaries)
    print(json.dumps([{k: v for k, v in row.items() if k in ("dataset", "status", "rows", "qa_rows", "jpeg_files")} for row in summaries]), flush=True)


if __name__ == "__main__":
    main()
