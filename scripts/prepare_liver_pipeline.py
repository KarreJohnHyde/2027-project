"""Wait for the selected MSD liver archive, verify, extract labelled pairs and inspect a manifest.

Training is separate. Original archives and interrupted files are preserved.
Only completed, checksum-matching labelled files are promoted into the cohort.
"""
import argparse
import hashlib
import json
from pathlib import Path, PurePosixPath
import shutil
import subprocess
import sys
import tarfile
import time
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = Path("C:/MedTwin_Datasets/Liver_MSD/download/Task03_Liver.tar")
DESTINATION = ROOT / "MedTwin_Datasets/Liver_MSD/Task03_Liver"
OUTPUT = ROOT / "_derived/datasets/msd-liver"
STATE = ROOT / "artifacts/downloads/liver_preparation_status.json"
EXPECTED_MD5 = "a90ec6c4aa7f6a3d087205e23d4e6397"
CHECKSUM_SOURCE = "https://github.com/Project-MONAI/MONAI/blob/dev/monai/apps/datasets.py"
RESERVE = 20 * 1024**3


def checksum(path, name="sha256"):
    result = hashlib.new(name)
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024**2), b""):
            result.update(block)
    return result.hexdigest()


def selected_members(archive):
    selected, seen = [], set()
    for member in archive.getmembers():
        name = PurePosixPath(member.name)
        if name.is_absolute() or ".." in name.parts or "\\" in member.name or ":" in member.name:
            raise ValueError("Unsafe archive member path")
        if not (member.isfile() or member.isdir()):
            raise ValueError("Archive links and special files are not permitted")
        if any(part.startswith("._") or part == "__MACOSX" for part in name.parts):
            continue
        if member.isdir():
            continue
        if name.parts[0] != "Task03_Liver":
            raise ValueError("Unexpected archive root")
        relative = PurePosixPath(*name.parts[1:])
        if relative.name.startswith("._"):
            continue
        wanted = str(relative) == "dataset.json" or (len(relative.parts) == 2 and relative.parts[0] in {"imagesTr", "labelsTr"} and relative.name.endswith(".nii.gz"))
        if not wanted:
            continue
        if str(relative).casefold() in seen or member.size <= 0:
            raise ValueError("Duplicate or empty labelled member")
        seen.add(str(relative).casefold())
        selected.append((member, relative))
    if "dataset.json" not in seen:
        raise ValueError("Missing dataset.json")
    return selected


def extract_labelled(source, destination, archive_sha, reserve=RESERVE):
    working = destination.with_name(destination.name + ".partial")
    if destination.is_symlink() or working.is_symlink():
        raise ValueError("Extraction directories must not be links")
    if destination.exists():
        record = json.loads((destination / "extraction.json").read_text())
        if record["archive_sha256"] != archive_sha:
            raise ValueError("Existing cohort belongs to another archive")
        for name, info in record["files"].items():
            if checksum(destination / name) != info["sha256"]:
                raise ValueError("Existing extracted file changed")
        return record
    working.mkdir(parents=True, exist_ok=True)
    marker = working / "source.json"
    if marker.exists() and json.loads(marker.read_text())["archive_sha256"] != archive_sha:
        raise ValueError("Interrupted extraction belongs to another archive")
    marker.write_text(json.dumps({"archive_sha256": archive_sha}))
    inventory = working / "files.json"
    completed = json.loads(inventory.read_text()) if inventory.exists() else {}
    with tarfile.open(source) as archive:
        selected = selected_members(archive)
        remaining = sum(m.size for m, n in selected if str(n) not in completed)
        if shutil.disk_usage(working).free < remaining + reserve:
            raise OSError("Extraction would breach the destination storage reserve")
        for member, name in selected:
            target = working / str(name)
            target.resolve().relative_to(working.resolve())
            target.parent.mkdir(parents=True, exist_ok=True)
            if str(name) in completed:
                if not target.is_file() or target.stat().st_size != member.size or checksum(target) != completed[str(name)]["sha256"]:
                    raise ValueError("Previously extracted bytes changed")
                continue
            partial = target.with_name(target.name + ".part")
            if partial.exists():
                partial.rename(partial.with_name(partial.name + f".interrupted-{time.time_ns()}"))
            if target.exists():
                raise ValueError("Untracked extracted file exists; preserved for review")
            with archive.extractfile(member) as stream, partial.open("xb") as output:
                shutil.copyfileobj(stream, output, 8 * 1024**2)
            if partial.stat().st_size != member.size:
                raise ValueError("Extracted member length mismatch")
            completed[str(name)] = {"bytes": member.size, "sha256": checksum(partial)}
            partial.replace(target)
            temporary = inventory.with_suffix(".tmp")
            temporary.write_text(json.dumps(completed, indent=2) + "\n")
            temporary.replace(inventory)
    record = {"archive_sha256": archive_sha, "files": completed, "scope": "Labelled imagesTr/labelsTr and original metadata only; unlabelled test images not extracted"}
    (working / "extraction.json").write_text(json.dumps(record, indent=2) + "\n")
    working.rename(destination)
    return record


def main():
    import msvcrt
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wait-hours", type=float, default=4)
    args = parser.parse_args()
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix(".lock").open("a+b") as lock:
        if STATE.with_suffix(".lock").stat().st_size == 0:
            lock.write(b"0"); lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("Liver preparation already running")
        def status(stage, **extra):
            data = {"stage": stage, "updated_at": datetime.now(timezone.utc).isoformat(), "clinical_validation": False, **extra}
            temporary = STATE.with_suffix(".tmp")
            temporary.write_text(json.dumps(data, indent=2) + "\n"); temporary.replace(STATE)
            print(json.dumps(data), flush=True)
        try:
            status("WAITING_FOR_VERIFIED_ARCHIVE")
            deadline = time.monotonic() + args.wait_hours * 3600
            while not ARCHIVE.is_file():
                if time.monotonic() > deadline:
                    raise TimeoutError("Archive is not ready; rerun after acquisition")
                time.sleep(10)
            status("VERIFYING_SOURCE_CHECKSUM")
            md5 = checksum(ARCHIVE, "md5")
            if md5 != EXPECTED_MD5:
                raise ValueError("Archive differs from MONAI's published MSD liver checksum")
            archive_sha = checksum(ARCHIVE)
            status("EXTRACTING_LABELLED_PAIRS", archive_sha256=archive_sha, published_md5=md5, checksum_source=CHECKSUM_SOURCE)
            extract_labelled(ARCHIVE, DESTINATION, archive_sha)
            sys.path.insert(0, str(ROOT))
            from prepare_msd_ct_datasets import prepare
            from ml_training.volumetric_manifest import read_pairs_csv, build_manifest, write_manifest
            status("MATCHING_ANNOTATIONS")
            summary = prepare(DESTINATION, OUTPUT)
            if "CC-BY-SA" not in str(summary["licence"]).upper().replace(" ", "-"):
                raise ValueError("Archive licence differs from expected published terms")
            evidence = OUTPUT / "licence_evidence.json"
            evidence.write_text(json.dumps({"datasets": [{"id": "msd-task03-liver", "license": {
                "name": summary["licence"], "authorization_status": "VERIFIED", "status": "PUBLISHED_IN_ARCHIVE",
                "authorization_reason": "Published MSD terms and owner instruction for local research preparation; commercial release requires a separate rights review",
                "source": "Task03_Liver/dataset.json"}}]}, indent=2))
            status("INSPECTING_VOXELS_AND_PATIENT_SPLITS", cases=summary["cases"])
            labels = {int(k): v for k, v in json.loads((OUTPUT / "labels.json").read_text()).items()}
            manifest = build_manifest(dataset_id="msd-task03-liver", dataset_root=DESTINATION,
                                      pairs=read_pairs_csv(OUTPUT / "pairs.csv", DESTINATION), labels=labels,
                                      seed=20261109, registry_path=evidence)
            path = OUTPUT / "manifest.json"
            write_manifest(manifest, path)
            subprocess.run([sys.executable, "scripts/register_msd_ct_dataset.py", "--archive", str(ARCHIVE), "--task-dir", str(DESTINATION),
                            "--dataset-id", "msd-task03-liver", "--task-id", "msd-liver-tumour-segmentation", "--system", "liver",
                            "--target", "Liver and tumour segmentation", "--title", "MSD Task03 Liver matched CT/mask cohort"], cwd=ROOT, check=True)
            registry_path = ROOT / "dataset_registry/tasks.json"
            registry = json.loads(registry_path.read_text())
            task = next(d for d in registry["datasets"] if d["id"] == "msd-task03-liver")["tasks"][0]
            task["preparation"] = {"manifest": str(path), "dataset_version": manifest["dataset_version"], "cases": summary["cases"], "clinical_validation": False}
            temporary = registry_path.with_suffix(".tmp"); temporary.write_text(json.dumps(registry, indent=2) + "\n"); temporary.replace(registry_path)
            status("PREPARED_NOT_CLINICALLY_VALIDATED", cases=summary["cases"], manifest=str(path), dataset_version=manifest["dataset_version"])
        except Exception as exc:
            status("FAILED_REQUIRES_REVIEW", error=f"{type(exc).__name__}: {exc}")
            raise


if __name__ == "__main__":
    main()
