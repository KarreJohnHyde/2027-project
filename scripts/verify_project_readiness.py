"""Read-only, checksum-based resource and model readiness audit; no patient data."""
from __future__ import annotations
import hashlib
import argparse
from importlib.metadata import version
import json
from pathlib import Path
import shutil
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))


def checksum(path, algorithm):
    if algorithm == "git_blob":
        result = hashlib.sha1(f"blob {path.stat().st_size}\0".encode())
    elif algorithm == "crc32c":
        import google_crc32c
        result = google_crc32c.Checksum()
    else:
        result = hashlib.new(algorithm)
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(8 * 1024**2), b""):
            result.update(chunk)
    value = result.hexdigest()
    return value.decode() if isinstance(value, bytes) else value


def audit():
    from app.services import model_registry, model_inference
    resources = []
    for name in ("public_acquisition", "multimodal_resources", "deepfluoro_resources"):
        manifest = json.loads((ROOT / f"dataset_registry/{name}.json").read_text())
        checked = 0
        total = 0
        failures = []
        for item in manifest["artifacts"]:
            if name == "deepfluoro_resources":
                path = Path(manifest["destination"]) / item["path"]
                algorithm = "sha256" if item["lfs_sha256"] else "git_blob"
                expected = item["lfs_sha256"] or item["git_oid"]
            else:
                directory = manifest["roots"][item["root"]] if "roots" in manifest else manifest["destination"]
                path = Path(directory) / item["relative_path"]
                algorithm, expected = item["hash_algorithm"], item["hash"]
            if not path.is_file():
                failures.append({"path": str(path), "reason": "MISSING"})
            elif path.stat().st_size != item["bytes"] or checksum(path, algorithm) != expected:
                failures.append({"path": str(path), "reason": "SIZE_OR_CHECKSUM_MISMATCH"})
            else:
                checked += 1
                total += item["bytes"]
        resources.append({"manifest": name, "expected": len(manifest["artifacts"]), "verified": checked, "bytes": total, "failures": failures})
        print(f"{name}: {checked}/{len(manifest['artifacts'])} verified", flush=True)
    entries = model_registry._load_registry()["models"]
    models = []
    for item in entries:
        gate = model_registry.activation_gate(item)
        kind = item.get("inference_input", "image_2d")
        models.append({"model_id": item["model_id"], "task": item["task"], "supported_modalities": item.get("supported_modalities", []),
                       "clinical_activation": gate["eligible"], "checkpoint_hash_matches": gate["checkpoint_hash_matches"],
                       "missing_declared_artifacts": gate["missing_artifacts"],
                       "upload_adapter_registered": bool(item.get("research_inference") and kind in model_inference.UPLOAD_INPUTS),
                       "inference_input": kind if item.get("research_inference") else None,
                       "research_gate": model_inference.research_gate(item) if item.get("research_inference") else None,
                       "inference_route": item.get("inference_route")})
    worker_path = ROOT / "artifacts/downloads/cohort_recovery_status.json"
    workers = json.loads(worker_path.read_text()) if worker_path.exists() else {"status": "NOT_RECORDED"}
    packages = {name: version(name) for name in ("torch", "monai", "scikit-learn", "torchio", "kornia", "highdicom", "trimesh", "diffdrr", "open-clip-torch", "TotalSegmentator", "medmnist")}
    return {"audited_at": datetime.now(timezone.utc).isoformat(), "resources": resources, "models": models, "software_versions": packages,
            "disk_free_gib": {drive: round(shutil.disk_usage(drive).free / 1024**3, 1) for drive in ("C:/", "D:/")},
            "ct_worker_last_reported_status": workers,
            "scope": "Pinned acquisition manifests and registered model artifacts only; not an inventory or endorsement of every medical dataset.",
            "all_requested_medical_capabilities_implemented": False,
            "blocking_gaps": ["No universal disease model or clinically activated model",
                              "LIDC subset is prepared; CQ500 has an unreadable source archive and liver acquisition/preparation remain unfinished",
                              "KiTS19 renal-tumour baseline failed its declared target and is blocked from uploads",
                              "CBIS ROI/full-image coordinates and DeepFluoro registration adapter require validation",
                              "Skin image/tabular fusion has internal holdout results only; broader multimodal fusion is not validated",
                              "No validated upload outcome forecast or causal treatment simulation",
                              "Offline learning benchmark does not authorize automatic retraining on uploads"]}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / f"artifacts/audits/project-readiness-{datetime.now(timezone.utc):%Y-%m-%d}.json")
    args = parser.parse_args()
    report = audit()
    target = args.output
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(f"Saved {target}")
    raise SystemExit(1 if any(row["failures"] for row in report["resources"]) else 0)
