"""Prepare exact RCC-AID series/mask pairs after verified acquisition. Never trains.

Commercial-development and clinical approval remain separate from this technical
inspection. Original ZIPs and publisher metadata are preserved, outside Git.
"""
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import shutil
import stat
import sys
import time
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DOWNLOAD = ROOT / "MedTwin_Datasets/RCC_AID/download"
OUTPUT = ROOT / "_derived/datasets/rcc-aid"
DESTINATION = ROOT / "MedTwin_Datasets/RCC_AID/paired"
STATE = ROOT / "artifacts/downloads/rcc_aid_preparation_status.json"
ACQUISITION = ROOT / "artifacts/downloads/rcc_aid_status.json"
RESERVE = 20 * 1024**3


def digest(path, algorithm="sha256"):
    result = hashlib.new(algorithm)
    with path.open("rb") as source:
        for block in iter(lambda: source.read(8 * 1024**2), b""):
            result.update(block)
    return result.hexdigest()


def metadata_pairs(rows):
    pairs, identities = [], set()
    for row in rows:
        series, patient, collection = row["SeriesInstanceUID"], row["PatientID"], row["Collection"]
        if (not re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", series) or series in identities
                or not re.fullmatch(r"[A-Za-z0-9-]+", patient)
                or collection not in {"TCGA-KIRC", "TCGA-KIRP", "TCGA-KICH"}
                or row["Modality"] != "CT"
                or row["LicenseURI"].rstrip("/") not in {"http://creativecommons.org/licenses/by/3.0", "https://creativecommons.org/licenses/by/3.0"}):
            raise ValueError("Duplicate, unsafe or unsupported publisher series/rights metadata")
        identities.add(series)
        stem = collection.removeprefix("TCGA-") + "_" + series.replace(".", "_")
        pairs.append({"patient_id": patient, "case_id": series,
                      "image_path": "images/" + stem + ".nii.gz",
                      "mask_path": "annotations/" + stem + "_seg.nii.gz"})
    if not pairs:
        raise ValueError("Empty publisher series inventory")
    return pairs


def index_archive(archive, expected):
    files = {}
    for member in archive.infolist():
        path = PurePosixPath(member.filename)
        mode = member.external_attr >> 16
        if (path.is_absolute() or ".." in path.parts or "\\" in member.filename or ":" in member.filename
                or stat.S_ISLNK(mode) or (mode and stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR})
                or member.flag_bits & 1):
            raise ValueError("Unsafe, linked or encrypted ZIP member")
        if member.is_dir():
            continue
        if member.filename in files or member.file_size <= 0 or member.filename not in expected:
            raise ValueError("Duplicate, empty or unexpected ZIP member")
        files[member.filename] = member
    if set(files) != set(expected):
        raise ValueError("ZIP inventory differs from exact metadata series identities")
    return files


def extract_pairs(download, destination, pairs, sources, reserve=RESERVE):
    working = destination.with_name(destination.name + ".partial")
    working.mkdir(parents=True, exist_ok=True)
    marker = working / "source.json"
    if marker.exists() and json.loads(marker.read_text()) != sources:
        raise ValueError("Interrupted extraction belongs to different source bytes")
    marker.write_text(json.dumps(sources, indent=2))
    inventory = working / "extraction.json"
    completed = json.loads(inventory.read_text()) if inventory.exists() else {}
    with zipfile.ZipFile(download / "images.zip") as images, zipfile.ZipFile(download / "annotations.zip") as masks:
        groups = [(images, index_archive(images, {p["image_path"] for p in pairs})),
                  (masks, index_archive(masks, {p["mask_path"] for p in pairs}))]
        required = sum(m.file_size for _, group in groups for name, m in group.items() if name not in completed)
        if shutil.disk_usage(working).free < required + reserve:
            raise OSError("Extraction would breach the 20 GiB storage reserve")
        for archive, group in groups:
            for name, member in group.items():
                target = working / name
                target.resolve().relative_to(working.resolve())
                target.parent.mkdir(parents=True, exist_ok=True)
                if name in completed:
                    if not target.is_file() or target.stat().st_size != member.file_size or digest(target) != completed[name]["sha256"]:
                        raise ValueError("Previously extracted bytes changed")
                    continue
                if target.exists():
                    raise ValueError("Untracked extracted file exists; preserved for review")
                partial = target.with_name(target.name + ".part")
                if partial.exists():
                    partial.rename(partial.with_name(partial.name + ".interrupted-" + str(time.time_ns())))
                with archive.open(member) as source, partial.open("xb") as stream:
                    shutil.copyfileobj(source, stream, 8 * 1024**2)
                if partial.stat().st_size != member.file_size:
                    raise ValueError("Extracted length mismatch")
                completed[name] = {"bytes": member.file_size, "sha256": digest(partial)}
                partial.replace(target)
                temporary = inventory.with_suffix(".tmp")
                temporary.write_text(json.dumps(completed, indent=2)); temporary.replace(inventory)
    working.rename(destination)


def main():
    import msvcrt
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix(".lock").open("a+b") as lock:
        if STATE.with_suffix(".lock").stat().st_size == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        def status(stage, **extra):
            payload = {"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat(),
                       "clinical_validation": False, "commercial_development_review": "NOT_REVIEWED", **extra}
            temporary = STATE.with_suffix(".tmp"); temporary.write_text(json.dumps(payload, indent=2)); temporary.replace(STATE)
            print(json.dumps(payload), flush=True)
        try:
            status("WAITING_FOR_VERIFIED_ACQUISITION")
            deadline = time.monotonic() + 4 * 3600
            while True:
                source = json.loads(ACQUISITION.read_text()) if ACQUISITION.exists() else {}
                if source.get("status") == "ACQUIRED_REQUIRES_PAIRING_AND_CURATION":
                    break
                if source.get("status") == "FAILED_REQUIRES_REVIEW" or time.monotonic() > deadline:
                    raise RuntimeError("Acquisition requires review or did not finish before preparation timeout")
                time.sleep(10)
            status("VERIFYING_SOURCE_BYTES")
            publisher = json.loads((DOWNLOAD.parent / "publisher_metadata.json").read_text())
            sources = {}
            for item in publisher["files"]:
                name = item["key"]
                if name not in {"images.zip", "annotations.zip", "metadata.csv", "manifest.tcia"}:
                    continue
                path = DOWNLOAD / name
                if path.stat().st_size != item["size"] or digest(path, "md5") != item["checksum"].removeprefix("md5:"):
                    raise ValueError("Publisher checksum/size mismatch")
                sources[name] = digest(path)
            if len(sources) != 4:
                raise ValueError("Publisher inventory is incomplete")
            with (DOWNLOAD / "metadata.csv").open(newline="") as handle:
                pairs = metadata_pairs(list(csv.DictReader(handle)))
            status("EXTRACTING_EXACT_SERIES_MASK_PAIRS", cases=len(pairs), patients=len({p["patient_id"] for p in pairs}))
            if DESTINATION.exists():
                if json.loads((DESTINATION / "source.json").read_text()) != sources:
                    raise ValueError("Existing cohort belongs to different sources")
                for name, item in json.loads((DESTINATION / "extraction.json").read_text()).items():
                    if digest(DESTINATION / name) != item["sha256"]:
                        raise ValueError("Extracted cohort changed")
            else:
                extract_pairs(DOWNLOAD, DESTINATION, pairs, sources)
            OUTPUT.mkdir(parents=True, exist_ok=True)
            with (OUTPUT / "pairs.csv").open("w", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(pairs[0])); writer.writeheader(); writer.writerows(pairs)
            evidence = OUTPUT / "source_rights_not_reviewed.json"
            evidence.write_text(json.dumps({"datasets": [{"id": "rcc-aid", "license": {
                "name": "Images/metadata CC BY 3.0; annotations CC BY 4.0",
                "source": "https://zenodo.org/records/19630298", "authorization_status": "UNVERIFIED",
                "status": "PUBLISHER_TERMS_RECORDED_COMMERCIAL_REVIEW_PENDING"}}]}, indent=2))
            status("INSPECTING_VOXELS_GEOMETRY_AND_PATIENT_SPLITS")
            sys.path.insert(0, str(ROOT))
            from ml_training.volumetric_manifest import build_manifest, write_manifest
            manifest = build_manifest(dataset_id="rcc-aid", dataset_root=DESTINATION, pairs=pairs,
                                      labels={0: "background", 1: "kidney", 2: "renal_tumour", 3: "renal_cyst"},
                                      seed=20261109, registry_path=evidence)
            manifest["provenance"]["publisher_archive_sha256"] = sources
            manifest["provenance"]["inventory_discrepancy"] = "Publisher prose: 129 scans/91 patients; actual CSV and annotation ZIP: 142 scans/101 patients. Exact source inventories govern matching."
            write_manifest(manifest, OUTPUT / "manifest.json")
            status("PREPARED_REQUIRES_CURATION_AND_RIGHTS_REVIEW", cases=len(pairs),
                   patients=manifest["validation"]["patient_count"], dataset_version=manifest["dataset_version"],
                   training_started=False, canonical_registry_mutated=False)
        except Exception as exc:
            status("FAILED_REQUIRES_REVIEW", error=f"{type(exc).__name__}: {exc}")
            raise


if __name__ == "__main__":
    main()
