"""Download a reviewed public-data manifest with resume, hashes and a disk reserve.

No credentials, account creation, licence prompts or remote code execution are used.
Run --plan to refresh pinned publisher metadata; --run downloads missing artifacts.
Existing GPU/download queues are independent. Dataset presence never enables a model.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "dataset_registry/public_acquisition.json"
STATE = ROOT / "artifacts/downloads/public_acquisition_status.json"
DATA = Path("C:/MedTwin_Datasets")
RESERVE = 60 * 1024**3  # space for the already-running downloads, extraction and caches
MEDMNIST = ("octmnist", "retinamnist", "dermamnist", "breastmnist", "pathmnist", "bloodmnist", "tissuemnist")


def now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def read_url(url):
    request = urllib.request.Request(url, headers={"User-Agent": "MedTwin-public-data/1.0"})
    with urllib.request.urlopen(request, timeout=60) as response:
        return response.read()


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def digest(path, algorithm="sha256"):
    if algorithm == "crc32c":
        # Kaggle's public Google Storage responses publish x-goog-hash=crc32c.
        # Castagnoli CRC is different from zlib's IEEE CRC32.
        import google_crc32c
        checksum = google_crc32c.Checksum()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(4 * 1024**2), b""):
                checksum.update(chunk)
        return checksum.hexdigest().decode("ascii")
    result = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(4 * 1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def plan():
    provenance = ROOT / "artifacts/downloads/provenance"
    artifacts = []
    github = json.loads(read_url("https://api.github.com/repos/neheller/kits19/commits/master"))["sha"]
    hf = json.loads(read_url("https://huggingface.co/api/datasets/neheller/KiTS-Challenge-Imaging"))["sha"]
    for name in ("README.md", "LICENSE", "data/LICENSE", "starter_code/get_imaging.py"):
        url = f"https://raw.githubusercontent.com/neheller/kits19/{github}/{name}"
        target = provenance / "kits19" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_url(url))
    licence = (provenance / "kits19/data/LICENSE").read_text()
    if "Attribution-NonCommercial-ShareAlike 4.0" not in licence:
        raise ValueError("KiTS19 publisher data licence changed; review required")
    images = json.loads(read_url(f"https://huggingface.co/api/datasets/neheller/KiTS-Challenge-Imaging/tree/{hf}/images?limit=1000"))
    by_case = {Path(item["path"]).name[:-7]: item for item in images if item["type"] == "file"}
    masks = sorted((ROOT / "data").glob("case_*/segmentation.nii*"))
    if len(masks) != 210:
        raise ValueError(f"Expected 210 existing KiTS19 masks, found {len(masks)}")
    for mask in masks:
        case = mask.parent.name
        item = by_case[case]
        artifacts.append({"dataset": "kits19", "relative_path": f"KiTS19/{case}/imaging.nii.gz",
                          "url": f"https://huggingface.co/datasets/neheller/KiTS-Challenge-Imaging/resolve/{hf}/{item['path']}",
                          "bytes": item["size"], "hash_algorithm": "sha256", "hash": item["lfs"]["oid"],
                          "mask_path": str(mask.relative_to(ROOT)).replace("\\", "/")})
    record = json.loads(read_url("https://zenodo.org/api/records/10519652"))
    files = {item["key"]: item for item in record["files"]}
    write_json(provenance / "medmnist/zenodo-record.json", record)
    info_url = "https://raw.githubusercontent.com/MedMNIST/MedMNIST/main/medmnist/info.py"
    # Save publisher metadata as text only; never execute downloaded Python.
    (provenance / "medmnist/info.py.txt").write_bytes(read_url(info_url))
    for name in MEDMNIST:
        item = files[f"{name}.npz"]
        algorithm, checksum = item["checksum"].split(":", 1)
        artifacts.append({"dataset": "medmnist-benchmarks", "relative_path": f"MedMNIST/{name}.npz",
                          "url": f"https://zenodo.org/records/10519652/files/{name}.npz?download=1",
                          "bytes": item["size"], "hash_algorithm": algorithm, "hash": checksum})
    kaggle_url = "https://www.kaggle.com/api/v1/datasets/view/paultimothymooney/chest-xray-pneumonia"
    kaggle = json.loads(read_url(kaggle_url))
    write_json(provenance / "kaggle-pneumonia/dataset-metadata.json", kaggle)
    result = {"schema_version": 1, "planned_at": now(), "destination": str(DATA), "reserve_bytes": RESERVE,
              "authorization": "Owner requested useful public dataset acquisition on 2026-11-06; local research only; retain publisher terms.",
              "datasets": [
                  {"id": "kits19", "source": "https://github.com/neheller/kits19", "github_revision": github,
                   "imaging_revision": hf, "license": "CC BY-NC-SA 4.0 (data); MIT (code)",
                   "purpose": "Complete the 210 existing kidney/tumour masks with matched CT volumes for the implemented volumetric trainer.",
                   "training_status": "Preparation and explicit task registration required after acquisition; no model is trained by this downloader."},
                  {"id": "medmnist-benchmarks", "source": "https://zenodo.org/records/10519652",
                   "license": "CC BY 4.0 except DermaMNIST: CC BY-NC 4.0", "subsets": list(MEDMNIST),
                   "purpose": "Small benchmark candidates for missing ophthalmology, dermatology, breast ultrasound and microscopy coverage.",
                   "training_status": "BENCHMARK_ONLY; 28-pixel images; not full-resolution clinical datasets, segmentation labels or independent evidence for existing models. Patient independence must be checked before reuse."},
                  {"id": "kaggle-pneumonia", "source": "https://www.kaggle.com/datasets/paultimothymooney/chest-xray-pneumonia",
                   "version": kaggle.get("currentVersionNumber"), "license": "CC BY 4.0 linked in publisher description",
                   "status": "REUSE_EXISTING", "existing_path": "chest_xray", "purpose": "Existing paediatric pneumonia research data; avoid another 1.2 GB download.",
                   "training_status": "Patient grouping and split audit required before training; not adult chest CT data."}],
              "artifacts": artifacts}
    write_json(MANIFEST, result)
    print(json.dumps({"manifest": str(MANIFEST), "artifacts": len(artifacts), "bytes": sum(a["bytes"] for a in artifacts)}), flush=True)


def download(item, root, reserve=RESERVE):
    target = (root / item["relative_path"]).resolve()
    target.relative_to(root.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if target.stat().st_size == item["bytes"] and digest(target, item["hash_algorithm"]) == item["hash"]:
            return "VERIFIED_PRESENT"
        raise ValueError(f"Existing final file differs from publisher: {target}")
    part = target.with_name(target.name + ".part")
    if part.exists() and part.stat().st_size > item["bytes"]:
        part.rename(part.with_name(part.name + f".invalid-{time.time_ns()}"))
    remaining = item["bytes"] - (part.stat().st_size if part.exists() else 0)
    if shutil.disk_usage(root).free < reserve + remaining:
        raise OSError("Disk reserve reached; resume after freeing space")
    for attempt in range(4):
        # curl handles HTTP Range and refuses a server that cannot resume instead of appending a full response.
        if not part.exists() or part.stat().st_size < item["bytes"]:
            command = ["curl.exe" if os.name == "nt" else "curl", "--location", "--fail", "--silent", "--show-error",
                       "--retry", "3", "--retry-all-errors", "--retry-delay", "5", "--connect-timeout", "30",
                       "--speed-time", "120", "--speed-limit", "1024", "--continue-at", "-", "--output", str(part), item["url"]]
            completed = subprocess.run(command, check=False)
            if completed.returncode:
                if completed.returncode in (33, 36) and part.exists():
                    # Some public hosts do not support Range. Keep the partial bytes,
                    # then retry a fresh transfer; never append a full response to them.
                    part.rename(part.with_name(part.name + f".resume-unsupported-{time.time_ns()}"))
                    continue
                if attempt == 3:
                    raise RuntimeError(f"curl failed with exit {completed.returncode}")
                time.sleep(5)
                continue
        if part.stat().st_size == item["bytes"] and digest(part, item["hash_algorithm"]) == item["hash"]:
            part.replace(target)
            return "DOWNLOADED_VERIFIED"
        part.rename(part.with_name(part.name + f".invalid-{time.time_ns()}"))
        raise ValueError(f"Publisher hash/size mismatch: {target.name}; corrupt bytes kept separately")
    raise RuntimeError("Download attempts exhausted")


def run(datasets=None):
    manifest = json.loads(MANIFEST.read_text())
    root = Path(manifest["destination"])
    root.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    # Windows closes this byte-range lock after a crash/reboot; stale lock files are harmless.
    lock = (STATE.parent / "public_acquisition.lock").open("a+b")
    if os.name == "nt":
        import msvcrt
        lock.seek(0)
        if not lock.read(1):
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            print("Another public acquisition worker is running.", flush=True)
            return 2
    state = json.loads(STATE.read_text()) if STATE.exists() else {"items": {}}
    state.update(status="RUNNING", started_at=now(), pid=os.getpid())
    failures = 0
    # Fetch small benchmarks first so useful completed files are available while the CT download runs.
    items = sorted(manifest["artifacts"], key=lambda a: (a["dataset"] == "kits19", a["bytes"]))
    items = [item for item in items if not datasets or item["dataset"] in datasets]
    try:
        for index, item in enumerate(items, 1):
            key = item["relative_path"]
            state.update(current=key, updated_at=now())
            write_json(STATE, state)
            print(f"{index}/{len(items)} {key} starting", flush=True)
            try:
                status = download(item, root, manifest["reserve_bytes"])
                state["items"][key] = {"status": status, "bytes": item["bytes"], "verified_at": now(), "hash": item["hash"]}
                print(f"{index}/{len(items)} {key} {status}", flush=True)
            except Exception as exc:
                failures += 1
                state["items"][key] = {"status": "FAILED", "error": str(exc), "updated_at": now()}
                print(f"{key} FAILED: {exc}", flush=True)
                if isinstance(exc, OSError):
                    state["status"] = "PAUSED_STORAGE_OR_IO"
                    break
            write_json(STATE, state)
        else:
            state["status"] = "COMPLETED" if failures == 0 else "INCOMPLETE_WITH_FAILURES"
    finally:
        state["updated_at"] = now()
        write_json(STATE, state)
        lock.close()
    print(state["status"], flush=True)
    return 0 if state["status"] == "COMPLETED" else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--dataset", action="append", choices=("kits19", "medmnist-benchmarks"))
    args = parser.parse_args()
    if args.plan:
        plan()
    return run(args.dataset) if args.run else 0


if __name__ == "__main__":
    sys.exit(main())
