"""Acquire publisher-pinned RCC-AID files; retain attribution and flag cohort curation.

Published terms: annotations CC BY 4.0; source images/metadata CC BY 3.0.
Acquisition is not clinical validation, commercial clearance or automatic training.
"""
from datetime import datetime, timezone
import csv
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / "MedTwin_Datasets/RCC_AID/download"
STATE = ROOT / "artifacts/downloads/rcc_aid_status.json"
SOURCE = ROOT / "artifacts/audits/rcc-aid-zenodo-metadata.json"
RESERVE = 20 * 1024**3


def hashes(path):
    md5, sha = hashlib.md5(), hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            md5.update(block); sha.update(block)
    return md5.hexdigest(), sha.hexdigest()


def main():
    import msvcrt
    DEST.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix(".lock").open("a+b") as lock:
        if STATE.with_suffix(".lock").stat().st_size == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("RCC-AID acquisition already running")
        metadata = json.loads(SOURCE.read_text())
        if metadata["metadata"].get("license", {}).get("id") != "cc-by-4.0":
            raise ValueError("Publisher annotation licence changed")
        state = {"status": "RUNNING", "pid": os.getpid(), "source": "https://zenodo.org/records/19630298",
                 "purpose": "Commercial-development candidate; clinical use and rights review not approved", "files": {}}
        def save():
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            temporary = STATE.with_suffix(".tmp"); temporary.write_text(json.dumps(state, indent=2) + "\n"); temporary.replace(STATE)
        save()
        try:
            for item in metadata["files"]:
                if item["key"] not in {"images.zip", "annotations.zip", "metadata.csv", "manifest.tcia"}:
                    continue
                target = DEST / item["key"]
                part = target.with_suffix(target.suffix + ".part")
                expected = item["checksum"].removeprefix("md5:")
                state["current"] = item["key"]; state["expected_bytes"] = item["size"]; save()
                if not target.exists():
                    if part.exists() and part.stat().st_size > item["size"]:
                        raise ValueError("Partial exceeds publisher size; preserved for review")
                    remaining = max(0, item["size"] - (part.stat().st_size if part.exists() else 0))
                    if shutil.disk_usage(DEST).free < remaining + RESERVE:
                        raise OSError("20 GiB destination reserve would be breached")
                    if remaining:
                        subprocess.run(["curl.exe", "--location", "--fail", "--silent", "--show-error", "--retry", "3", "--retry-all-errors",
                                        "--connect-timeout", "30", "--max-time", "14400", "--continue-at", "-",
                                        "--output", str(part), item["links"]["self"]], check=True)
                    candidate = part
                else:
                    candidate = target
                md5, sha = hashes(candidate)
                if candidate.stat().st_size != item["size"] or md5 != expected:
                    raise ValueError("Publisher byte count or MD5 mismatch; file preserved for review")
                if item["key"].endswith(".zip"):
                    with zipfile.ZipFile(candidate) as archive:
                        if archive.testzip():
                            raise ValueError("ZIP CRC mismatch")
                if candidate == part:
                    part.replace(target)
                state["files"][item["key"]] = {"bytes": item["size"], "publisher_md5": md5, "sha256": sha, "status": "VERIFIED"}
                save()
            rows = list(csv.DictReader((DEST / "metadata.csv").open()))
            state.update(status="ACQUIRED_REQUIRES_PAIRING_AND_CURATION", metadata_rows=len(rows), patients=len({r["PatientID"] for r in rows}),
                         description_count_discrepancy="Publisher prose says 129 scans / 91 patients; current CSV and annotation inventory contain 142 scans / 101 patients. Do not silently substitute the prose counts.")
            (DEST.parent / "ATTRIBUTION.html").write_text(metadata["metadata"]["description"], encoding="utf-8")
            shutil.copy2(SOURCE, DEST.parent / "publisher_metadata.json")
            save()
        except Exception as exc:
            state.update(status="FAILED_REQUIRES_REVIEW", error=f"{type(exc).__name__}: {exc}"); save(); raise
        print(json.dumps({"status": state["status"], "files": len(state["files"])}))


if __name__ == "__main__":
    main()
