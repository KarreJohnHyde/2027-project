"""Acquire the permissioned DeepFluoro DICOM remix for paired 2D/3D research.

The original data licence is CC BY-NC 4.0, separate from the original GPL code.
Downloads data only; does not execute upstream code or unpickle pose objects.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from acquire_public_datasets import ROOT, digest, now, read_url, write_json

REPO = "eigenvivek/xvr-data"
DESTINATION = ROOT / "MedTwin_Datasets/DeepFluoro"
MANIFEST = ROOT / "dataset_registry/deepfluoro_resources.json"
STATE = ROOT / "artifacts/downloads/deepfluoro_status.json"
RESERVE = 20 * 1024**3


def plan():
    info = json.loads(read_url(f"https://huggingface.co/api/datasets/{REPO}"))
    revision = info["sha"]
    url = f"https://huggingface.co/api/datasets/{REPO}/tree/{revision}/deepfluoro?recursive=true&limit=1000"
    entries = []
    while url:
        with urllib.request.urlopen(url, timeout=60) as response:
            entries += json.load(response)
            link = response.headers.get("Link", "")
        match = re.search(r'<([^>]+)>;\s*rel="next"', link)
        url = match.group(1) if match else None
    selected = [item for item in entries if item["type"] == "file" and "/segmentations/" not in item["path"]]
    licence = read_url(f"https://huggingface.co/datasets/{REPO}/resolve/{revision}/deepfluoro/LICENSE").decode()
    if not licence.startswith("Attribution-NonCommercial 4.0 International"):
        raise ValueError("DeepFluoro-specific data licence changed; do not infer it from the mixed repository's root licence")
    items = [{"path": item["path"], "bytes": item["size"], "lfs_sha256": item.get("lfs", {}).get("oid"), "git_oid": item["oid"]} for item in selected]
    provenance = ROOT / "artifacts/downloads/provenance/multimodal/deepfluoro"
    provenance.mkdir(parents=True, exist_ok=True)
    (provenance / "DATA_LICENSE.txt").write_text(licence, encoding="utf-8")
    # Preserve the original project's documentation/licence without installing its GPL code.
    commit = json.loads(read_url("https://api.github.com/repos/rg2/DeepFluoroLabeling-IPCAI2020/commits/master"))["sha"]
    for name in ("README.md", "hdf5_layouts/Readme.md", "LICENSE"):
        target = provenance / "original-project" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(read_url(f"https://raw.githubusercontent.com/rg2/DeepFluoroLabeling-IPCAI2020/{commit}/{name}"))
    manifest = {"schema_version": 1, "planned_at": now(), "dataset": "DeepFluoro, xvr-data DICOM remix",
                "source": "https://github.com/rg2/DeepFluoroLabeling-IPCAI2020", "mirror": "https://huggingface.co/datasets/" + REPO,
                "revision": revision, "original_project_revision": commit, "licence": "CC BY-NC 4.0, data; original GPL code is not installed",
                "permission_provenance": "The xvr dataset publication states that the DICOM remix is hosted with permission from the original authors; the deepfluoro/LICENSE file declares CC BY-NC 4.0.",
                "destination": str(DESTINATION), "reserve_bytes": RESERVE, "artifacts": items,
                "purpose": "Paired CT, real fluoroscopy DICOM, 2D masks/3D masks, fiducials and pose metadata for localization and 2D/3D registration research",
                "selection": "All deepfluoro resources except the older single-label 2D segmentations; the multichannel masks retain overlapping structures.",
                "limitations": "Six cadaveric pelvic specimens, not a broad clinical cohort. Split by specimen and retain acquisition geometry. Frame/pose conventions still require an explicit adapter/protocol. No registration model is trained or activated."}
    write_json(MANIFEST, manifest)
    print(json.dumps({"manifest": str(MANIFEST), "files": len(items), "bytes": sum(item["bytes"] for item in items)}), flush=True)


def run():
    os.environ["HF_HUB_DISABLE_TELEMETRY"] = "1"
    os.environ["HF_HUB_DISABLE_XET"] = "1"
    import msvcrt
    import shutil
    from huggingface_hub import snapshot_download
    import nibabel as nib
    import numpy as np
    manifest = json.loads(MANIFEST.read_text())
    DESTINATION.mkdir(parents=True, exist_ok=True)
    STATE.parent.mkdir(parents=True, exist_ok=True)
    lock = (STATE.parent / "deepfluoro_acquisition.lock").open("a+b")
    lock.seek(0)
    if not lock.read(1):
        lock.write(b"0")
        lock.flush()
    lock.seek(0)
    try:
        msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        print("DeepFluoro acquisition already running", flush=True)
        return 2
    missing = sum(item["bytes"] for item in manifest["artifacts"] if not (DESTINATION / item["path"]).is_file())
    if shutil.disk_usage(DESTINATION).free < RESERVE + missing:
        raise OSError("Insufficient D: space above the 20 GiB reserve")
    state = {"status": "DOWNLOADING", "pid": os.getpid(), "started_at": now(), "expected_files": len(manifest["artifacts"]),
             "expected_bytes": sum(i["bytes"] for i in manifest["artifacts"]), "destination": str(DESTINATION)}
    write_json(STATE, state)
    try:
        snapshot_download(REPO, repo_type="dataset", revision=manifest["revision"], token=False, local_dir=str(DESTINATION),
                          allow_patterns=["deepfluoro/**"], ignore_patterns=["deepfluoro/*/segmentations/*"], max_workers=4)
        state.update(status="VERIFYING", verified_files=0)
        write_json(STATE, state)
        for index, item in enumerate(manifest["artifacts"], 1):
            target = (DESTINATION / item["path"]).resolve()
            target.relative_to(DESTINATION.resolve())
            if target.stat().st_size != item["bytes"]:
                raise ValueError("DeepFluoro artifact size differs from pinned metadata")
            if item["lfs_sha256"]:
                if digest(target) != item["lfs_sha256"]:
                    raise ValueError("DeepFluoro LFS SHA-256 mismatch")
            else:
                data = target.read_bytes()
                if hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() != item["git_oid"]:
                    raise ValueError("DeepFluoro pinned Git blob mismatch")
            if index % 25 == 0:
                state.update(verified_files=index, updated_at=now())
                write_json(STATE, state)
        specimens = []
        for directory in sorted((DESTINATION / "deepfluoro").glob("subject*")):
            volume, mask = nib.load(directory / "volume.nii.gz"), nib.load(directory / "mask.nii.gz")
            if volume.shape != mask.shape or not np.allclose(volume.affine, mask.affine, atol=1e-3):
                raise ValueError("Remixed CT/mask geometry mismatch")
            xrays = sorted((directory / "xrays").glob("*.dcm"))
            if not xrays or any(not path.with_suffix(".pt").is_file() for path in xrays):
                raise ValueError("X-ray/pose file join is incomplete")
            specimens.append({"specimen": directory.name, "ct_shape": list(volume.shape), "xrays": len(xrays),
                              "multichannel_masks": len(list((directory / "segmentations_multichannel").glob("*.pt")))})
        if len(specimens) != 6:
            raise ValueError("Expected six DeepFluoro specimens")
        state.update(status="COMPLETED_VERIFIED", verified_files=len(manifest["artifacts"]), specimens=specimens,
                     limitations="Header/file-join checks only; pose .pt files were not unpickled. Coordinate adapter, specimen split and registration evaluation remain required.")
        print(json.dumps({"status": state["status"], "files": state["verified_files"], "specimens": specimens}), flush=True)
    except Exception as exc:
        state.update(status="INCOMPLETE_REQUIRES_RETRY", error=str(exc))
        raise
    finally:
        state["updated_at"] = now()
        write_json(STATE, state)
        lock.close()
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", action="store_true")
    parser.add_argument("--run", action="store_true")
    args = parser.parse_args()
    if args.plan:
        plan()
    sys.exit(run() if args.run else 0)
