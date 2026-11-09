"""Resume the already-selected LIDC, CQ500 and MSD liver cohorts using native HTTPS.

Archives remain local and are not extracted automatically. Completion requires
archive checks, not a downloader exit code. Source metadata and local SHA-256s
are retained; an S3 multipart ETag is never described as a publisher SHA-256.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import time
import zipfile
from urllib.parse import urlencode

from acquire_public_datasets import now, write_json

ROOT = Path(__file__).resolve().parents[1]
DATA = Path("C:/MedTwin_Datasets")
STATE = ROOT / "artifacts/downloads/cohort_recovery_status.json"
RESERVE = 60 * 1024**3


def remote_size(url):
    result = subprocess.run(["curl.exe", "--head", "--location", "--fail", "--silent", "--show-error",
                             "--connect-timeout", "20", "--max-time", "90", url], capture_output=True, text=True, check=True)
    lengths = [int(line.split(":", 1)[1]) for line in result.stdout.splitlines() if line.lower().startswith("content-length:")]
    if not lengths or lengths[-1] <= 0:
        raise ValueError("Source did not supply a positive Content-Length")
    return lengths[-1]


def sha256(path):
    result = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
            result.update(chunk)
    return result.hexdigest()


def check_archive(path, expected_images=None):
    if path.name.endswith((".zip", ".zip.part")):
        with zipfile.ZipFile(path) as archive:
            members = archive.infolist()
            bad = archive.testzip()
            if bad:
                raise ValueError(f"Archive CRC failed: {bad}")
            dcms = sum(item.filename.lower().endswith(".dcm") for item in members)
            if expected_images is not None and dcms != expected_images:
                raise ValueError(f"Expected {expected_images} DICOM slices; found {dcms}")
            if not dcms:
                raise ValueError("No DICOM images in cohort archive")
        return {"members": len(members), "dicom_images": dcms, "integrity": "ZIP_CRC_AND_LOCAL_SHA256"}
    with tarfile.open(path, "r:") as archive:
        members = list(archive)
        names = {item.name.removeprefix("./") for item in members}
        if "Task03_Liver/dataset.json" not in names:
            raise ValueError("Missing MSD liver dataset.json")
        member = next(item for item in members if item.name.removeprefix("./") == "Task03_Liver/dataset.json")
        metadata = json.load(archive.extractfile(member))
        expected = int(metadata["numTraining"])
        pairs = 0
        for row in metadata["training"]:
            for key in ("image", "label"):
                name = "Task03_Liver/" + row[key].removeprefix("./")
                if name not in names:
                    raise ValueError(f"Missing MSD member: {name}")
            pairs += 1
        if pairs != expected:
            raise ValueError("MSD training pair count differs from metadata")
    return {"members": len(members), "labelled_pairs": pairs,
            "integrity": "TAR_HEADER_AND_PAIR_INVENTORY_PLUS_LOCAL_SHA256_NOT_PUBLISHER_CHECKSUM"}


def acquire(url, target, expected_bytes=None, expected_images=None):
    target = target.resolve()
    target.relative_to(DATA.resolve())
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if expected_bytes is not None and target.stat().st_size > expected_bytes:
            raise ValueError("Existing archive exceeds remote size; preserved for review")
        try:
            checks = check_archive(target, expected_images)
            if expected_bytes is None or target.stat().st_size == expected_bytes:
                return {"status": "VERIFIED_EXISTING", "bytes": target.stat().st_size,
                        "local_sha256": sha256(target), **checks}
        except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError):
            pass
        # Preserve unfinished old output in the resumable name without deleting data.
        part = target.with_name(target.name + ".part")
        if part.exists():
            raise ValueError("Both final and partial files exist; review required")
        target.rename(part)
    part = target.with_name(target.name + ".part")
    if part.exists() and expected_bytes is not None and part.stat().st_size == expected_bytes:
        try:
            checks = check_archive(part, expected_images)
        except (tarfile.TarError, zipfile.BadZipFile, EOFError, OSError, ValueError):
            # A complete-sized interrupted file can still be corrupt. Appending
            # zero bytes cannot repair it. Retain it before a fresh transfer.
            if shutil.disk_usage(target.parent).free < RESERVE + expected_bytes:
                raise OSError("Storage reserve reached before replacing a corrupt partial archive")
            part.rename(part.with_name(part.name + f".invalid-{time.time_ns()}"))
        else:
            result = {"status": "VERIFIED_RECOVERED_PARTIAL", "bytes": part.stat().st_size,
                      "local_sha256": sha256(part), **checks}
            part.replace(target)
            return result
    remaining = max(0, (expected_bytes or 512 * 1024**2) - (part.stat().st_size if part.exists() else 0))
    if shutil.disk_usage(target.parent).free < RESERVE + remaining:
        raise OSError("60 GiB storage reserve would be breached")
    command = ["curl.exe", "--location", "--fail", "--silent", "--show-error", "--retry", "3",
                    "--retry-all-errors", "--retry-delay", "5", "--connect-timeout", "30",
                    "--max-time", "14400", "--speed-time", "120", "--speed-limit", "1024",
                    "--continue-at", "-", "--output", str(part), url]
    completed = subprocess.run(command, check=False)
    if completed.returncode in (33, 36) and part.exists():
        # NBIA may serve a fresh ZIP without HTTP Range support. Preserve the
        # interrupted response, then retry from byte zero rather than append it.
        if shutil.disk_usage(target.parent).free < RESERVE + (expected_bytes or 512 * 1024**2):
            raise OSError("Storage reserve reached before a fresh non-Range transfer")
        part.rename(part.with_name(part.name + f".range-unsupported-{time.time_ns()}"))
        completed = subprocess.run(command, check=False)
    completed.check_returncode()
    if expected_bytes is not None and part.stat().st_size != expected_bytes:
        raise ValueError("Downloaded byte count differs from source Content-Length")
    checks = check_archive(part, expected_images)
    result = {"status": "DOWNLOADED_ARCHIVE_VERIFIED", "bytes": part.stat().st_size,
              "local_sha256": sha256(part), **checks}
    part.replace(target)
    return result


def cohort_items(name):
    if name == "lidc":
        selected = json.loads((DATA / "LIDC/selected_series.json").read_text())
        for row in selected:
            uid = row["SeriesInstanceUID"]
            yield {"id": row["PatientID"], "target": DATA / "LIDC/series" / f"{row['PatientID']}__{uid}.zip",
                   "url": "https://services.cancerimagingarchive.net/nbia-api/services/v1/getImage?" + urlencode({"SeriesInstanceUID": uid}),
                   "expected_images": int(row["ImageCount"])}
    elif name == "cq500":
        with (DATA / "CQ500/reads.csv").open(newline="", encoding="utf-8-sig") as handle:
            names = sorted({row["name"] for row in csv.DictReader(handle)})
        for scan in names:
            if not scan.startswith("CQ500-CT-") or not scan.removeprefix("CQ500-CT-").isdigit():
                raise ValueError("Unexpected CQ500 scan identifier")
            yield {"id": scan, "target": DATA / "CQ500/zips" / f"{scan}.zip",
                   "url": f"https://s3.ap-south-1.amazonaws.com/qure.headct.study/{scan}.zip"}
    elif name == "liver":
        yield {"id": "Task03_Liver", "target": DATA / "Liver_MSD/download/Task03_Liver.tar",
               "url": "https://msd-for-monai.s3-us-west-2.amazonaws.com/Task03_Liver.tar"}


def main(names):
    import msvcrt

    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock = STATE.with_suffix(".lock").open("a+b")
    if STATE.with_suffix(".lock").stat().st_size == 0:
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        raise SystemExit("A cohort recovery worker already holds the lock")
    state = {"status": "RUNNING", "pid": os.getpid(), "started_at": now(), "reserve_bytes": RESERVE,
             "source_terms": {"lidc": "CC BY 3.0", "cq500": "CC BY-NC-SA 4.0", "liver": "CC BY-SA 4.0"},
             "scope": "Existing selected cohorts only; archives retained, training and extraction separate.", "cohorts": {}}
    write_json(STATE, state)
    try:
        for name in names:
            items = list(cohort_items(name))
            group = state["cohorts"][name] = {"status": "RUNNING", "expected": len(items), "items": {}}
            for item in items:
                state.update(current=f"{name}/{item['id']}", updated_at=now())
                write_json(STATE, state)
                try:
                    expected = remote_size(item["url"]) if name != "lidc" else None
                    result = acquire(item["url"], item["target"], expected, item.get("expected_images"))
                    group["items"][item["id"]] = {**result, "source": item["url"], "verified_at": now()}
                    print(f"{name}/{item['id']}: {result['status']}", flush=True)
                except Exception as exc:
                    group["items"][item["id"]] = {"status": "FAILED", "error": str(exc)}
                    print(f"{name}/{item['id']}: FAILED {exc}", flush=True)
                    if isinstance(exc, OSError):
                        group["status"] = "PAUSED_STORAGE_OR_IO"
                        break
                write_json(STATE, state)
            else:
                group["status"] = "COMPLETE_ARCHIVES_VERIFIED" if all(
                    value["status"] != "FAILED" for value in group["items"].values()) else "INCOMPLETE"
        state["status"] = "COMPLETE_ARCHIVES_VERIFIED" if all(
            value["status"] == "COMPLETE_ARCHIVES_VERIFIED" for value in state["cohorts"].values()) else "INCOMPLETE"
    finally:
        state["updated_at"] = now()
        write_json(STATE, state)
        lock.close()
    return 0 if state["status"] == "COMPLETE_ARCHIVES_VERIFIED" else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cohort", choices=("lidc", "cq500", "liver"), action="append")
    args = parser.parse_args()
    raise SystemExit(main(args.cohort or ["lidc", "cq500", "liver"]))
