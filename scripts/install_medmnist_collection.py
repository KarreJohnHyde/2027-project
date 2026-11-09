"""Install the official 18 lightweight MedMNIST benchmarks, with verified files and CSV indexes.

Reuses existing NPZs. No model is trained or activated. Image arrays stay in NPZs;
only one preview per split is exported to avoid duplicating 718k images on disk.
"""
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from acquire_public_datasets import download, digest, now, write_json

MANIFEST = ROOT / "dataset_registry/medmnist_collection.json"
STATE = ROOT / "artifacts/downloads/medmnist_collection_status.json"
DATA = Path("C:/MedTwin_Datasets/MedMNIST")
OUT = ROOT / "_derived/datasets/medmnist"
SOURCE = "https://zenodo.org/records/10519652"


def plan():
    from medmnist import INFO

    provenance = ROOT / "artifacts/downloads/provenance/medmnist-10519652.json"
    provenance.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl.exe", "--fail", "--location", "--silent", "--show-error",
                    "--connect-timeout", "20", "--max-time", "120", "--output", str(provenance),
                    "https://zenodo.org/api/records/10519652"], check=True)
    metadata = json.loads(provenance.read_text(encoding="utf-8"))
    files = {item["key"]: item for item in metadata["files"]}
    artifacts = []
    for name, info in INFO.items():
        item = files[f"{name}.npz"]
        if item["checksum"] != "md5:" + info["MD5"]:
            raise ValueError(f"Publisher and installed loader checksums disagree: {name}")
        artifacts.append({"dataset": name, "relative_path": f"{name}.npz",
                          "url": f"{SOURCE}/files/{name}.npz?download=1", "bytes": item["size"],
                          "hash_algorithm": "md5", "hash": info["MD5"], "license": info["license"],
                          "task": info["task"], "labels": info["label"], "split_counts": info["n_samples"],
                          "dimensions": 3 if name.endswith("3d") else 2})
    manifest = {"schema_version": 1, "planned_at": now(), "source": SOURCE, "release": "3.0",
                "destination": str(DATA), "derived_destination": str(OUT), "reserve_bytes": 60 * 1024**3,
                "purpose": "Free lightweight 2D/3D classification benchmarks; reuse existing seven subsets.",
                "limitations": ["Not intended for clinical use; 28-pixel images or 28-cubed volumes.",
                                "Organ labels identify anatomy, not every disease in each organ.",
                                "No segmentation masks, scanner geometry or universal patient IDs.",
                                "Publisher splits preserved; patient-independent external validation is not established.",
                                "Related source datasets may overlap existing cohorts; not independent external evidence.",
                                "DermaMNIST is CC BY-NC 4.0; remaining subsets are CC BY 4.0; retain source citations."],
                "artifacts": artifacts}
    write_json(MANIFEST, manifest)
    print(f"Planned {len(artifacts)} official NPZ files", flush=True)


def prepare(item, path, output):
    import numpy as np
    from PIL import Image

    output.mkdir(parents=True, exist_ok=True)
    temporary = output / "samples.csv.part"
    counts = {}
    with np.load(path, allow_pickle=False) as arrays, temporary.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=["dataset", "split", "array_file", "array_key", "array_index", "labels_json"])
        writer.writeheader()
        for split in ("train", "val", "test"):
            images, labels = arrays[f"{split}_images"], arrays[f"{split}_labels"]
            expected = item["split_counts"][split]
            if len(images) != expected or len(labels) != expected or images.dtype != np.uint8:
                raise ValueError(f"Unexpected arrays/counts: {item['dataset']}/{split}")
            if tuple(images.shape[1:1 + item["dimensions"]]) != (28,) * item["dimensions"]:
                raise ValueError("Unexpected benchmark image dimensions")
            if not np.isfinite(labels).all():
                raise ValueError("Non-finite labels")
            if not np.equal(labels, np.floor(labels)).all():
                raise ValueError("Non-integer classification labels")
            if "multi-label" in item["task"]:
                if labels.shape[1:] != (len(item["labels"]),) or not np.isin(labels, (0, 1)).all():
                    raise ValueError("Invalid multi-label targets")
            elif labels.min() < 0 or labels.max() >= len(item["labels"]):
                raise ValueError("Classification label outside declared categories")
            counts[split] = len(images)
            for index, label in enumerate(labels):
                writer.writerow({"dataset": item["dataset"], "split": split, "array_file": str(path),
                                 "array_key": f"{split}_images", "array_index": index,
                                 "labels_json": json.dumps(label.tolist(), separators=(",", ":"))})
            preview = images[0]
            if item["dimensions"] == 3:
                preview = preview[preview.shape[0] // 2]
            Image.fromarray(preview).save(output / f"{split}_preview.png")
    temporary.replace(output / "samples.csv")
    report = {"dataset": item["dataset"], "source": SOURCE, "source_md5": item["hash"],
              "local_sha256": digest(path), "license": item["license"], "split_counts": counts,
              "labels": item["labels"], "task": item["task"], "dimensions": item["dimensions"],
              "status": "VERIFIED_BENCHMARK_ONLY", "clinical_validated": False,
              "patient_independence": "NOT_ESTABLISHED", "prepared_at": now()}
    write_json(output / "preparation.json", report)
    return report


def run():
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    root = Path(manifest["destination"])
    root.mkdir(parents=True, exist_ok=True)
    state = {"status": "RUNNING", "started_at": now(), "items": {}}
    write_json(STATE, state)
    summaries = []
    for item in manifest["artifacts"]:
        name = item["dataset"]
        try:
            acquisition = download(item, root, manifest["reserve_bytes"])
            report = prepare(item, root / item["relative_path"], OUT / name)
            summaries.append(report)
            state["items"][name] = {"status": acquisition, "prepared": True, "bytes": item["bytes"],
                                     "sha256": report["local_sha256"], "verified_at": now()}
            print(f"{name}: {acquisition}; indexed {sum(report['split_counts'].values())} samples", flush=True)
        except Exception as exc:
            state["items"][name] = {"status": "FAILED", "error": str(exc)}
            print(f"{name}: FAILED {exc}", flush=True)
        state["updated_at"] = now()
        write_json(STATE, state)
    state["status"] = "COMPLETED_VERIFIED" if len(summaries) == len(manifest["artifacts"]) else "INCOMPLETE"
    state["samples_indexed"] = sum(sum(row["split_counts"].values()) for row in summaries)
    state["updated_at"] = now()
    write_json(STATE, state)
    write_json(OUT / "preparation.json", summaries)
    print(json.dumps({k: v for k, v in state.items() if k != "items"}), flush=True)
    return 0 if state["status"] == "COMPLETED_VERIFIED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.plan:
        plan()
    if args.run:
        import msvcrt
        STATE.parent.mkdir(parents=True, exist_ok=True)
        with STATE.with_suffix(".lock").open("a+b") as lock:
            lock.seek(0)
            if not lock.read(1):
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            try:
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError:
                raise SystemExit("Another MedMNIST installation worker is running")
            raise SystemExit(run())
