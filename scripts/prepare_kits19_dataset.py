"""Reconcile the acquired KiTS19 CTs and original masks into a checked training manifest.

Original data are preserved. Masks are losslessly gzip-compressed beside the CTs
so one bounded dataset root contains every pair. This does not train a model.
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from ml_training.volumetric_manifest import build_manifest, write_manifest

DATASET_ID = "kits19-labels"
SOURCE = ROOT / "dataset_registry/public_acquisition.json"
REGISTRY = ROOT / "dataset_registry/tasks.json"
OUT = ROOT / "_derived/datasets/kits19-segmentation"


def hash_stream(handle):
    result = hashlib.sha256()
    for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
        result.update(chunk)
    return result.hexdigest()


def copy_mask(source: Path, target: Path):
    with source.open("rb") as handle:
        original = hash_stream(handle)
    if target.exists():
        with gzip.open(target, "rb") as handle:
            if hash_stream(handle) != original:
                raise ValueError(f"Existing compressed mask differs from original: {target.name}")
        return original
    if shutil.disk_usage(target.parent).free < 60 * 1024**3 + source.stat().st_size:
        raise OSError("C: storage reserve reached before mask preparation")
    temporary = target.with_name(target.name + ".part")
    with source.open("rb") as incoming, temporary.open("wb") as raw:
        with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as outgoing:
            shutil.copyfileobj(incoming, outgoing, length=8 * 1024**2)
    with gzip.open(temporary, "rb") as handle:
        if hash_stream(handle) != original:
            raise ValueError("Mask compression did not preserve original bytes")
    temporary.replace(target)
    return original


def main():
    manifest = json.loads(SOURCE.read_text(encoding="utf-8"))
    root = (Path(manifest["destination"]) / "KiTS19").resolve()
    items = [item for item in manifest["artifacts"] if item["dataset"] == "kits19"]
    if len(items) != 210:
        raise ValueError("Expected the acquired 210 labelled KiTS19 cases")
    OUT.mkdir(parents=True, exist_ok=True)
    pairs, provenance = [], []
    for item in items:
        image = (Path(manifest["destination"]) / item["relative_path"]).resolve()
        image.relative_to(root)
        mask = (ROOT / item["mask_path"]).resolve()
        mask.relative_to((ROOT / "data").resolve())
        with image.open("rb") as handle:
            if image.stat().st_size != item["bytes"] or hash_stream(handle) != item["hash"]:
                raise ValueError(f"CT no longer matches pinned publisher checksum: {image.parent.name}")
        target = image.parent / "segmentation.nii.gz"
        source_sha = copy_mask(mask, target)
        case = image.parent.name
        pairs.append({"patient_id": case, "case_id": case, "image_path": image.relative_to(root).as_posix(),
                      "mask_path": target.relative_to(root).as_posix()})
        provenance.append({"case_id": case, "source_mask_sha256": source_sha, "source_mask": str(mask)})
        print(f"{case}: CT checksum and lossless mask copy verified", flush=True)

    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    record = next(item for item in registry["datasets"] if item["id"] == DATASET_ID)
    licence = {**record["license"], "authorization_status": "VERIFIED",
               "authorization_scope": "Local non-commercial research training and evaluation; no commercial release permission inferred.",
               "authorization_reason": "Published KiTS19 CC BY-NC-SA 4.0 terms and owner instruction to prepare and train on 2026-11-09.",
               "source": "https://github.com/neheller/kits19/blob/master/data/LICENSE"}
    # A temporary evidence registry lets the manifest record the verified rights
    # while the canonical task remains blocked until every pair passes inspection.
    candidate = {"datasets": [{**record, "license": licence}]}
    temporary_registry = OUT / "licence_evidence.json"
    temporary_registry.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
    result = build_manifest(dataset_id=DATASET_ID, dataset_root=root, pairs=pairs,
                            labels={0: "background", 1: "kidney", 2: "renal_tumour"}, seed=20261109,
                            registry_path=temporary_registry)
    target_manifest = OUT / "manifest.json"
    write_manifest(result, target_manifest)
    with (OUT / "pairs.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(pairs[0]))
        writer.writeheader()
        writer.writerows(pairs)
    (OUT / "mask_provenance.json").write_text(json.dumps(provenance, indent=2) + "\n", encoding="utf-8")
    (OUT / "labels.json").write_text(json.dumps({0: "background", 1: "kidney", 2: "renal_tumour"}) + "\n", encoding="utf-8")
    # Read again at publication time to preserve other independently prepared tasks.
    registry = json.loads(REGISTRY.read_text(encoding="utf-8"))
    record = next(item for item in registry["datasets"] if item["id"] == DATASET_ID)
    record.update(title="KiTS19 matched kidney and renal-tumour CT/mask cohort (210 cases)",
                  location=str(root), license=licence, labels="PAIRED_CT_AND_MASKS",
                  identity="210 checksum-verified acquired CT volumes paired with losslessly compressed original kidney/tumour masks",
                  cases_count=len(pairs))
    record["tasks"] = [{"task_id": "kits19-kidney-tumour-segmentation", "type": "SEGMENTATION_VOLUMES",
                        "target": "Kidney and renal-tumour masks on acquired contrast CT", "training_eligible": True,
                        "validation_ready": True, "readiness": "READY_FOR_TRAINING", "flags": ["TASK_SUPPORTED_BY_LABELS"],
                        "preparation": {"manifest": str(target_manifest), "cases": len(pairs),
                                        "split_policy": result.get("split_policy"), "clinical_validation": False}}]
    REGISTRY.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"manifest": str(target_manifest), "cases": len(pairs), "status": "PREPARED_NOT_CLINICALLY_VALIDATED"}), flush=True)


if __name__ == "__main__":
    main()
