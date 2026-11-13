"""Prepare controlled, nonexecuting model-development experiments.

By default imports no ML runtime, changes no registries and never launches a trainer. The
trainer is declared executable only if its source supports development-only
execution AND the existing live permission gate succeeds. The gate is not
reimplemented or replaced here.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FAMILIES = [
    {"family": "kidney_tumour", "dataset_id": "kits19-labels", "manifest": "kits19-segmentation/manifest.json",
     "trainer": "ml_training.volumetric_multichannel", "channels": ["CT"], "intensity": "ct", "spacing": [3, 3, 3],
     "variants": [{"name": "matched_baseline", "foreground_probability": 0.6, "class_weights": None},
                  {"name": "weighted_loss", "foreground_probability": 0.6, "class_weights": [0.1, 1, 4]},
                  {"name": "foreground_sampling", "foreground_probability": 0.85, "class_weights": None}],
     "measure": ["per-class validation Dice", "lesion recall", "false-positive components", "tumour-size breakdown"],
     "notice": "The original FAILED checkpoint remains blocked; the exposed 32-patient test is not a new untouched test."},
    {"family": "stroke", "dataset_id": "isles-2022", "manifest": "isles22-dwi-adc/manifest.json",
     "trainer": "ml_training.volumetric_multichannel", "channels": ["DWI", "ADC"], "intensity": "mr", "spacing": [2, 2, 2],
     "variants": [{"name": "matched_baseline", "foreground_probability": 0.6, "class_weights": None},
                  {"name": "lesion_sampling", "foreground_probability": 0.85, "class_weights": None}],
     "measure": ["validation Dice", "lesion recall/F1", "false positives/case", "lesion-size breakdown"]},
    {"family": "fracture", "dataset_id": "bone-fracture-roboflow-v4", "manifest": "bone-fracture-detection/samples.csv",
     "trainer": "ml_training.detect", "task_id": "bone-fracture-detection", "modality": "XRAY", "anatomy": "bones",
     "variants": [{"name": "matched_baseline", "min_size": 512, "max_size": 1024},
     {"name": "small_target_resolution", "min_size": 768, "max_size": 1280}],
     "measure": ["validation AP50:95", "recall", "precision", "false positives/image", "small-target recall"]},
    {"family": "stenosis", "dataset_id": "arcade", "manifest": "arcade-stenosis-detection/samples.csv",
     "trainer": "ml_training.detect", "task_id": "arcade-stenosis-detection", "modality": "ANGIOGRAPHY", "anatomy": "heart",
     "variants": [{"name": "matched_baseline", "min_size": 512, "max_size": 1024},
     {"name": "small_target_resolution", "min_size": 768, "max_size": 1280}],
     "measure": ["validation AP50:95", "recall", "precision", "false positives/image", "negative-region audit"]},
    {"family": "skin", "dataset_id": "pad-ufes-20", "manifest": "pad-clinical-image/samples.csv", "trainer": "ml_training.skin_fusion",
     "variants": [{"name": "matched_image_baseline", "arm": "image_only"}, {"name": "matched_fusion_baseline", "arm": "image_tabular"}],
     "measure": ["validation macro F1", "per-class support/recall", "patient-paired arm difference", "Brier/ECE"],
     "notice": "Keep fitted encoders/scalers training-only. Validate a sampling/loss change before declaring improvement."},
    {"family": "gastrovision", "dataset_id": "gastrovision", "manifest": "gastrovision-27class/samples.csv", "trainer": "ml_training.classify",
     "task_id": "gastrovision-27class", "modality": "ENDOSCOPY", "anatomy": "intestines",
     "variants": [{"name": "unweighted_comparison", "class_weighting": "none"},
                  {"name": "inverse_frequency", "class_weighting": "inverse_frequency"}],
     "measure": ["validation macro F1", "per-class sensitivity/support", "confusion matrix", "Brier/ECE"]},
]


def prepare(root: Path) -> dict:
    registry_path = root / "dataset_registry/tasks.json"
    registry = json.loads(registry_path.read_text(encoding="utf-8-sig"))
    purpose = json.loads((root / "dataset_registry/release_context.json").read_text())["training_purpose"]
    by_id = {item["id"]: item for item in registry["datasets"]}
    experiments = []
    for family in FAMILIES:
        item = dict(family)
        manifest = root / "_derived/datasets" / item.pop("manifest")
        source = root / (item["trainer"].replace(".", "/") + ".py")
        source_text = source.read_text(encoding="utf-8")
        dataset = by_id.get(item["dataset_id"])
        license_info = (dataset or {}).get("license", {})
        # A safety-oriented preparation result: no generic trainer permission inference.
        blockers = []
        if not manifest.is_file():
            blockers.append("PREPARED_MANIFEST_MISSING")
        if not dataset:
            blockers.append("DATASET_NOT_IN_CANONICAL_REGISTRY")
        dev_safe = '"--development-only"' in source_text
        if not dev_safe:
            blockers.append("TRAINER_CURRENTLY_EVALUATES_TEST_AND_PUBLISHES_NO_SAFE_DEVELOPMENT_ONLY_MODE")
        if purpose == "commercial_development":
            blockers.append("EXISTING_EVIDENCE_BOUND_COMMERCIAL_TRAINING_GATE_MUST_APPROVE_BEFORE_EXECUTION")
        item.update(manifest=str(manifest), manifest_present=manifest.is_file(), trainer_source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
                    manifest_sha256=hashlib.sha256(manifest.read_bytes()).hexdigest() if manifest.is_file() else None,
                    development_only_supported=dev_safe, execution_status="PREPARED_NOT_EXECUTED", execution_allowed=False,
                    blockers=blockers, license_record=license_info, split_policy="TRAIN_ONLY_FITTING_VALIDATION_ONLY_SELECTION_NO_TEST_EVALUATION",
                    checkpoint_policy="NEW_EXPERIMENT_DIRECTORY_ONLY_NO_OVERWRITE_NO_REGISTRY_PUBLICATION",
                    same_validation_protocol=True, seed=20261113, max_epochs=2, iterations_per_epoch=10,
                    final_evaluation="REQUIRES_UNTOUCHED_INDEPENDENT_COHORT_AFTER_SELECTION")
        if dev_safe and manifest.is_file() and item["trainer"] == "ml_training.volumetric_multichannel":
            commands = []
            for variant in item["variants"]:
                out = root / "artifacts/review-2026-11-13" / f"data-experiment-{item['family']}-{variant['name']}"
                command = [".venv/Scripts/python.exe", "-m", item["trainer"], "train", "--manifest", str(manifest), "--output-dir", str(out),
                           "--model-id", f"review_{item['family']}_{variant['name']}", "--channel-names", *item["channels"],
                           "--intensity", item["intensity"], "--epochs", "2", "--iterations-per-epoch", "10", "--validate-every", "1",
                           "--workers", "0", "--seed", "20261113", "--patch-size", "96", "96", "64", "--target-spacing", *map(str, item["spacing"]),
                           "--foreground-probability", str(variant["foreground_probability"]), "--development-only"]
                if variant["class_weights"]:
                    command.extend(["--class-weights", *map(str, variant["class_weights"])])
                commands.append({"variant": variant["name"], "argv": command,
                                 "notice": "Preparation only. Existing trainer enforces live rights; this command may and should refuse when approval is absent."})
            item["development_commands"] = commands
        elif dev_safe and manifest.is_file():
            commands = []
            for variant in item["variants"]:
                command = [".venv/Scripts/python.exe", "-m", item["trainer"], "--task-id", item["task_id"],
                           "--model-id", f"review_{item['family']}_{variant['name']}", "--display-name", f"Review {item['family']} {variant['name']}",
                           "--modality", item["modality"], "--anatomy", item["anatomy"], "--development-only", "--epochs", "2",
                           "--workers", "0", "--batch-size", "2", "--seed", "20261113", "--max-train-samples", "64", "--max-val-samples", "32"]
                if item["trainer"] == "ml_training.detect":
                    command.extend(["--min-size", str(variant["min_size"]), "--max-size", str(variant["max_size"])])
                    if item["family"] == "fracture":
                        command.extend(["--yolo-classes", "0,1,2,3,5,6", "--class-name", "fracture"])
                    else:
                        command.extend(["--category", "stenosis", "--class-name", "stenosis"])
                else:
                    command.extend(["--archs", "efficientnet_b0", "--class-weighting", variant["class_weighting"], "--exploratory"])
                commands.append({"variant": variant["name"], "argv": command,
                                 "notice": "Preparation only; deterministic development subset and same seed across variants. Existing live rights gate must approve; class-absent or leaking subsets must refuse."})
            item["development_commands"] = commands
        experiments.append(item)
    return {"schema_version": "medtwin-controlled-experiments-v1", "generated_at": datetime.now(timezone.utc).isoformat(),
            "training_purpose": purpose, "registry_sha256": hashlib.sha256(registry_path.read_bytes()).hexdigest(),
            "experiments": experiments, "new_accuracy_measurements": False, "training_launched": False,
            "notice": "Prepared bounded comparisons, not successful model improvements. No test data selection, model activation, permission changes or original checkpoint overwrite."}


def verify_live_rights(result: dict, root: Path) -> None:
    """Call the existing gate, without creating data loaders or training jobs."""
    sys.path.insert(0, str(root))
    from ml_training.volumetric_manifest import enforce_training_license
    for item in result["experiments"]:
        try:
            evidence = enforce_training_license({"dataset_id": item["dataset_id"]}, root / "dataset_registry/tasks.json")
            item["live_training_gate"] = {"status": "PASSED", "evidence": evidence,
                                           "notice": "No experiment was launched by preparation."}
        except PermissionError as exc:
            item["live_training_gate"] = {"status": "BLOCKED", "exception": type(exc).__name__, "reason": str(exc)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--output", type=Path, default=ROOT / "artifacts/review-2026-11-13/data-experiments.json")
    parser.add_argument("--verify-rights", action="store_true", help="Execute the existing rights gate only; no training or data loading")
    args = parser.parse_args()
    result = prepare(args.root.resolve())
    if args.verify_rights:
        verify_live_rights(result, args.root.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(args.output), "prepared": len(result["experiments"]), "training_launched": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
