"""Durable bounded KiTS19 experiment: train, evaluate, publish research bundle, verify parity.

No clinical activation or commercial permission is granted. The existing trainer
resumes matching checkpoints. Progress survives this chat; process restart still
requires rerunning this script. Only this experiment's process lock is claimed.
"""
import json
import argparse
import hashlib
import os
from pathlib import Path
import subprocess
import sys
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
STATE = ROOT / "artifacts/training/kits19-pipeline-status.json"
RUN = ROOT / "artifacts/training/ct_kidney_tumour_segresnet-20261109"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--resume-publish", action="store_true", help="Resume artifact publication after completed frozen train/test; never rerun the test for this continuation")
    args = parser.parse_args()
    import msvcrt
    STATE.parent.mkdir(parents=True, exist_ok=True)
    with STATE.with_suffix(".lock").open("a+b") as lock:
        if STATE.with_suffix(".lock").stat().st_size == 0:
            lock.write(b"0")
            lock.flush()
        lock.seek(0)
        try:
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise SystemExit("KiTS19 experiment already running")
        manifest = ROOT / "_derived/datasets/kits19-segmentation/manifest.json"
        cohort = json.loads(manifest.read_text(encoding="utf-8"))
        completed_path = RUN / "execution.json"
        if completed_path.exists():
            previous_execution = json.loads(completed_path.read_text())
            if (previous_execution.get("execution_status") == "COMPLETE"
                    and previous_execution.get("model_id") == "ct_kidney_tumour_segresnet"
                    and previous_execution.get("dataset_version") == cohort["dataset_version"]
                    and previous_execution.get("manifest_sha256") == hashlib.sha256(manifest.read_bytes()).hexdigest()):
                args.resume_publish = True
        state = {"status": "RUNNING", "pid": os.getpid(), "dataset_version": cohort["dataset_version"],
                 "started_at": datetime.now(timezone.utc).isoformat(), "scope": "Initial research experiment; no external/clinical validation", "steps": {}}
        if args.resume_publish:
            execution = json.loads((RUN / "execution.json").read_text())
            if (execution.get("execution_status") != "COMPLETE" or execution.get("model_id") != "ct_kidney_tumour_segresnet"
                    or execution.get("dataset_version") != cohort["dataset_version"]
                    or execution.get("manifest_sha256") != hashlib.sha256(manifest.read_bytes()).hexdigest()):
                raise SystemExit("Publication continuation requires this cohort's completed frozen experiment")
            state["steps"]["train_and_internal_test"] = {"status": "PASSED", "exit_code": 0, "continuation": "Existing complete execution; not rerun"}
        steps = [
            ("train_and_internal_test", ["-m", "ml_training.volumetric_multichannel", "train", "--manifest", str(manifest),
                "--output-dir", str(RUN), "--model-id", "ct_kidney_tumour_segresnet", "--channel-names", "CT",
                "--intensity", "ct", "--epochs", "20", "--iterations-per-epoch", "60", "--batch-size", "2",
                "--patch-size", "96", "96", "96", "--target-spacing", "3", "3", "3", "--init-filters", "8",
                "--validate-every", "5", "--workers", "0", "--seed", "20261109", "--amp", "--device", "cuda",
                "--cache-dir", str(ROOT / "_derived/cache/kits19-3mm"),
                "--volume-semantics", "Research voxel-count volumes on one CT; no histologic diagnosis or clinical tumour staging."]),
            ("publish_research_bundle", ["scripts/publish_brain_mri_models.py", "--profile", "kidney", "--run-dir", str(RUN)]),
            ("measure_offline_adapter_parity", ["scripts/verify_volumetric_serving_parity.py", "--model-id", "ct_kidney_tumour_segresnet", "--offline-evaluation-only"]),
            ("refresh_commercial_inventory", ["scripts/commercial_license_review.py"]),
            ("refresh_coverage", ["scripts/export_capability_coverage.py"]),
            ("refresh_registry_gates", ["scripts/write_validation_status.py"]),
        ]
        if args.resume_publish:
            steps = steps[1:]
        def save():
            state["updated_at"] = datetime.now(timezone.utc).isoformat()
            temporary = STATE.with_suffix(".tmp")
            temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            temporary.replace(STATE)
        save()
        for name, arguments in steps:
            state["current"] = name
            save()
            print(f"Starting {name}", flush=True)
            result = subprocess.run([sys.executable, "-u", *arguments], cwd=ROOT)
            state["steps"][name] = {"exit_code": result.returncode,
                                     "status": ("MEASURED" if name == "measure_offline_adapter_parity" else "PASSED") if result.returncode == 0 else "FAILED"}
            if result.returncode:
                state["status"] = "FAILED_REQUIRES_REVIEW"
                save()
                return result.returncode
            save()
        model = next(m for m in json.loads((ROOT / "model_registry/models.json").read_text())["models"] if m["model_id"] == "ct_kidney_tumour_segresnet")
        state["research_quality_assessment"] = model.get("research_quality_assessment")
        state["status"] = "RESEARCH_EXPERIMENT_REJECTED_FAILED_TARGET" if model["status"] == "FAILED" else "RESEARCH_EXPERIMENT_COMPLETE_NOT_CLINICALLY_VALIDATED"
        save()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
