"""Held-out report for a cardiac cine-MRI volumetric segmenter: overlap, surface distance and cardiac indices.

Reads a completed ``ml_training.volumetric`` run (execution.json and the saved held-out predictions) and
its manifest. For every frozen-test case it scores the right-ventricular cavity, myocardium and
left-ventricular cavity (Dice from the run, 3-D HD95 and ASSD in millimetres here). For every test patient
it derives LV and RV end-diastolic and end-systolic volumes, ejection fractions and the LV myocardial mass
(myocardial volume x 1.05 g/mL at end-diastole) from the predicted and the reference masks, and reports
their agreement (bias, 95% limits of agreement, mean absolute error, Pearson r) with patient-bootstrap
intervals. Voxel volume comes from the NIfTI header pixdim: in these files the sform affine is unit-scaled,
so spacing derived from the affine would understate volumes. Writes the evaluation report, the model card
and the registry entry (research-only; there is no upload inference path for volumes).

  python -m ml_training.volumetric_report --run-dir artifacts/training/<run> --model-id acdc_cardiac_mri_3d_unet
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import nibabel as nib
import numpy as np
from scipy import ndimage

from ml_training.common import MODEL_CARDS, REPORTS, ROOT, bootstrap_ci, checkpoint_ref, register_model, relative

MYOCARDIAL_DENSITY_G_PER_ML = 1.05
STRUCTURES = {1: "right_ventricular_cavity", 2: "myocardium", 3: "left_ventricular_cavity"}


def surface_distances(reference: np.ndarray, prediction: np.ndarray, spacing: tuple[float, ...]) -> dict | None:
    """Symmetric 3-D surface distances in millimetres (None when either mask is empty)."""
    if not reference.any() or not prediction.any():
        return None
    surface_a = reference & ~ndimage.binary_erosion(reference, border_value=0)
    surface_b = prediction & ~ndimage.binary_erosion(prediction, border_value=0)
    to_b = ndimage.distance_transform_edt(~surface_b, sampling=spacing)[surface_a]
    to_a = ndimage.distance_transform_edt(~surface_a, sampling=spacing)[surface_b]
    return {"hd95_mm": float(max(np.percentile(to_b, 95), np.percentile(to_a, 95))),
            "assd_mm": float((to_b.sum() + to_a.sum()) / (len(to_b) + len(to_a)))}


def agreement(predicted: list[float], reference: list[float], groups: np.ndarray) -> dict:
    p, r = np.asarray(predicted, dtype=float), np.asarray(reference, dtype=float)
    difference = p - r
    sd = float(difference.std(ddof=1)) if len(difference) > 1 else 0.0
    bias = float(difference.mean())
    return {
        "n_patients": int(len(p)), "reference_mean": float(r.mean()), "predicted_mean": float(p.mean()),
        "bias": bias, "limits_of_agreement": [bias - 1.96 * sd, bias + 1.96 * sd],
        "mean_absolute_error": float(np.abs(difference).mean()),
        "mean_absolute_error_95ci": bootstrap_ci(lambda idx: float(np.abs(difference[idx]).mean()), len(p), groups, unit="patient"),
        "pearson_r": float(np.corrcoef(p, r)[0, 1]) if len(p) > 2 and p.std() > 0 and r.std() > 0 else None,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--task-id", default="acdc-cardiac-segmentation")
    args = parser.parse_args()

    run_dir = args.run_dir if args.run_dir.is_absolute() else ROOT / args.run_dir
    execution = json.loads((run_dir / "execution.json").read_text(encoding="utf-8"))
    if execution.get("execution_status") != "COMPLETE" or not execution.get("held_out_predictions"):
        raise SystemExit("The run is not complete or was run without --save-predictions.")
    manifest = json.loads(Path(execution["manifest_path"]).read_text(encoding="utf-8"))
    tasks = json.loads((ROOT / "dataset_registry" / "tasks.json").read_text(encoding="utf-8"))
    dataset, task = next((d, t) for d in tasks["datasets"] for t in d["tasks"] if t["task_id"] == args.task_id)
    if dataset["id"] != manifest["dataset_id"] or task["preparation"]["dataset_version"] != manifest["dataset_version"]:
        raise SystemExit("The run's manifest does not match the audited task (dataset id or version differs).")

    root = Path(manifest["dataset_root"])
    by_case = {case["case_id"]: case for case in manifest["cases"]}
    predictions = Path(execution["held_out_predictions"])
    cases = []
    for scored in execution["held_out_test"]["cases"]:
        case = by_case[scored["case_id"]]
        image = nib.load(str(root / case["image_path"]))
        zooms = tuple(float(z) for z in image.header.get_zooms()[:3])
        reference = np.asarray(nib.load(str(root / case["mask_path"])).dataobj).round().astype(np.int16)
        predicted = np.asarray(nib.load(str(predictions / f"{scored['case_id']}.nii.gz")).dataobj).astype(np.int16)
        if reference.shape != predicted.shape:
            raise SystemExit(f"{scored['case_id']}: prediction and reference shapes differ.")
        voxel_ml = float(np.prod(zooms)) / 1000.0
        structures = {}
        for label, name in STRUCTURES.items():
            distances = surface_distances(reference == label, predicted == label, zooms)
            structures[name] = {
                "dice": scored["classes"][str(label)]["dice"], "iou": scored["classes"][str(label)]["iou"],
                "reference_ml": float((reference == label).sum() * voxel_ml), "predicted_ml": float((predicted == label).sum() * voxel_ml),
                **(distances or {"hd95_mm": None, "assd_mm": None}),
            }
        cases.append({"case_id": scored["case_id"], "patient_id": scored["patient_id"], "phase": case["phase"], "spacing_mm": list(zooms), "structures": structures})

    # Overlap and surface distance, bootstrapped over patients (two phases per patient).
    groups = np.array([case["patient_id"] for case in cases])
    per_structure = {}
    for name in STRUCTURES.values():
        dice = np.array([np.nan if case["structures"][name]["dice"] is None else case["structures"][name]["dice"] for case in cases])
        hd95 = [case["structures"][name]["hd95_mm"] for case in cases if case["structures"][name]["hd95_mm"] is not None]
        assd = [case["structures"][name]["assd_mm"] for case in cases if case["structures"][name]["assd_mm"] is not None]
        per_structure[name] = {
            "mean_dice": float(np.nanmean(dice)), "mean_dice_95ci": bootstrap_ci(lambda idx: float(np.nanmean(dice[idx])), len(dice), groups, unit="patient"),
            "mean_dice_ed": float(np.nanmean([d for d, c in zip(dice, cases) if c["phase"] == "ED"])),
            "mean_dice_es": float(np.nanmean([d for d, c in zip(dice, cases) if c["phase"] == "ES"])),
            "mean_hd95_mm": float(np.mean(hd95)) if hd95 else None, "mean_assd_mm": float(np.mean(assd)) if assd else None,
            "cases_with_surface_distance": len(hd95),
        }
    macro = np.array([np.nanmean([case["structures"][name]["dice"] for name in STRUCTURES.values() if case["structures"][name]["dice"] is not None]) for case in cases])

    # Cardiac indices per patient, from predicted and from reference masks.
    patients = sorted({case["patient_id"] for case in cases})
    phase = {(case["patient_id"], case["phase"]): case["structures"] for case in cases}
    indices = {key: ([], []) for key in ("lv_edv_ml", "lv_esv_ml", "lv_ef_percent", "rv_edv_ml", "rv_esv_ml", "rv_ef_percent", "lv_myocardial_mass_g")}
    complete = [patient for patient in patients if (patient, "ED") in phase and (patient, "ES") in phase]
    for patient in complete:
        ed, es = phase[(patient, "ED")], phase[(patient, "ES")]
        for source, column in (("predicted_ml", 0), ("reference_ml", 1)):
            lv_edv, lv_esv = ed["left_ventricular_cavity"][source], es["left_ventricular_cavity"][source]
            rv_edv, rv_esv = ed["right_ventricular_cavity"][source], es["right_ventricular_cavity"][source]
            values = {"lv_edv_ml": lv_edv, "lv_esv_ml": lv_esv, "lv_ef_percent": 100 * (lv_edv - lv_esv) / lv_edv if lv_edv else np.nan,
                      "rv_edv_ml": rv_edv, "rv_esv_ml": rv_esv, "rv_ef_percent": 100 * (rv_edv - rv_esv) / rv_edv if rv_edv else np.nan,
                      "lv_myocardial_mass_g": ed["myocardium"][source] * MYOCARDIAL_DENSITY_G_PER_ML}
            for key, value in values.items():
                indices[key][column].append(float(value))
    patient_groups = np.array(complete)
    clinical = {key: agreement(predicted, reference, patient_groups) for key, (predicted, reference) in indices.items()}

    checkpoint = Path(execution["checkpoint"]["path"])
    run_id = run_dir.name
    epochs = execution.get("epochs") or []
    license_info = dataset["license"]
    report = {
        "model_id": args.model_id, "run_id": run_id, "task_id": args.task_id, "task_type": "volumetric_segmentation",
        "dataset": dataset["title"], "dataset_id": dataset["id"], "dataset_version": manifest["dataset_version"], "dataset_license": license_info,
        "split_method": task["preparation"]["split_method"], "split_counts": manifest["validation"]["cases_per_split"],
        "patients_per_split": manifest["validation"]["patients_per_split"], "leakage_exclusions": manifest["split_policy"].get("leakage_exclusions"),
        "test_n": len(cases), "test_patients": len(patients),
        "selection": execution["selection"], "config": execution["config"], "epochs_run": len(epochs),
        "metrics": {"mean_case_macro_dice": float(np.nanmean(macro)), "mean_case_macro_dice_95ci": bootstrap_ci(lambda idx: float(np.nanmean(macro[idx])), len(macro), groups, unit="patient"),
                    "per_structure": per_structure},
        "clinical_indices": clinical, "clinical_index_definitions": {
            "volumes": "voxel count x voxel volume (NIfTI header pixdim) at the publisher's end-diastolic (ED) and end-systolic (ES) frames",
            "ejection_fraction": "(EDV - ESV) / EDV x 100", "myocardial_mass": f"ED myocardial volume x {MYOCARDIAL_DENSITY_G_PER_ML} g/mL",
            "reference": "the same indices from the publisher's reference masks (not from clinical reports)"},
        "spacing_note": "Voxel spacing is read from the NIfTI header pixdim (for example 1.56 x 1.56 x 10 mm); the files' sform affine is unit-scaled.",
        "benchmark_context": ("Leading entries of the publisher's challenge (Bernard et al., IEEE TMI 2018) reported substantially higher overlap and "
                              "ejection-fraction agreement; this from-scratch 3-D baseline is not competitive with them. Context only."),
        "cases": cases,
        "checkpoint": {"path": checkpoint_ref(checkpoint), "sha256": execution["checkpoint"]["sha256"]},
        "held_out_predictions": checkpoint_ref(predictions),
        "determinism": execution["config"].get("deterministic_algorithms"),
        "reporting_context": {"dataset": dataset["title"], "dataset_version": manifest["dataset_version"][:16], "split": "test", "checkpoint": f"sha256:{execution['checkpoint']['sha256']}"},
        "validation_readiness": {"validation_ready": False, "readiness": "INTERNAL_HELD_OUT_ONLY", "run_scope": "RESEARCH"},
        "limitations": [
            "Internal held-out evaluation on the publisher's test patients from one centre; no external or clinical validation.",
            "Cardiac indices are compared with indices from the publisher's reference masks, not with clinically reported values.",
            "Native acquisition grid without resampling; slice thickness (5-10 mm) limits through-plane accuracy, and HD95 is dominated by it.",
            "No connected-component post-processing was prespecified; predicted regions away from the heart inflate volumes and HD95, so "
            "volumes, ejection fractions and myocardial mass carry large biases and wide limits of agreement.",
            "Evaluation and training used float16 autocast on CUDA; CUDA cross-entropy is not deterministic, so a rerun can differ slightly.",
            "Research-only output; there is no upload inference path, and nothing here is a patient measurement.",
        ],
    }
    REPORTS.mkdir(parents=True, exist_ok=True)
    report_path = REPORTS / f"{args.model_id}.json"
    report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")

    def ci(interval: dict) -> str:
        return f"{interval['low']:.3f}-{interval['high']:.3f}" if interval.get("status") == "COMPUTED" else "not computed"

    lvef = clinical["lv_ef_percent"]
    card = [
        "# Model card: Cardiac cine-MRI ventricular segmenter, 3-D (research)", "",
        f"- **Model id:** `{args.model_id}` (registry status `READY_UNVALIDATED`; research-only; no upload inference path)",
        "- **Task:** segmentation of the right-ventricular cavity, myocardium and left-ventricular cavity at end-diastole and end-systole.",
        f"- **Data:** dataset version `{manifest['dataset_version'][:16]}`; {task['preparation']['split_method']}. Sources and terms: Data sources and licences.",
        f"- **Architecture:** 3-D U-Net, channels {execution['config']['channels']}, patch {execution['config']['patch_size']}, trained from scratch; best validation epoch {execution['selection']['best_epoch']} of {len(epochs)}.",
        f"- **Checkpoint:** `{checkpoint_ref(checkpoint)}`, SHA-256 `{execution['checkpoint']['sha256']}`.",
        "", f"## Held-out test results ({len(patients)} patients, {len(cases)} ED/ES volumes, evaluated once)", "",
        f"- Mean case macro Dice {report['metrics']['mean_case_macro_dice']:.3f} (95% CI {ci(report['metrics']['mean_case_macro_dice_95ci'])}).",
        *[f"- {name.replace('_', ' ')}: Dice {item['mean_dice']:.3f} (95% CI {ci(item['mean_dice_95ci'])}); HD95 {item['mean_hd95_mm'] or 0:.1f} mm." for name, item in per_structure.items()],
        f"- LV ejection fraction vs reference masks: bias {lvef['bias']:+.1f} points, limits of agreement {lvef['limits_of_agreement'][0]:+.1f} to {lvef['limits_of_agreement'][1]:+.1f}, MAE {lvef['mean_absolute_error']:.1f} (n = {lvef['n_patients']}).",
        "", "## Limitations", "", *[f"- {item}" for item in report["limitations"]], "", f"Full report: `{relative(report_path)}`.",
    ]
    MODEL_CARDS.mkdir(parents=True, exist_ok=True)
    (MODEL_CARDS / f"{args.model_id}.md").write_text("\n".join(card) + "\n", encoding="utf-8")

    registry = {model["model_id"]: model for model in json.loads((ROOT / "model_registry" / "models.json").read_text(encoding="utf-8"))["models"]}
    entry = dict(registry.get(args.model_id) or {})
    entry.update({
        "model_id": args.model_id, "task": "volumetric_semantic_segmentation", "status": "READY_UNVALIDATED", "validated": False,
        "research_inference": True, "inference_input": "volume_nifti", "weights_path": checkpoint_ref(checkpoint),
        "limitations": report["limitations"], "validation_readiness": report["validation_readiness"],
        "pipeline": {**(entry.get("pipeline") or {}), "real_data_training_executed": True, "run_id": run_id, "report_builder": "python -m ml_training.volumetric_report"},
        "artifact_bundle": {
            **(entry.get("artifact_bundle") or {}), "dataset_version": manifest["dataset_version"], "dataset_license": license_info["name"],
            "split_manifest_path": relative(Path(execution["manifest_path"])), "preprocessing_version": execution["config"]["preprocessing_version"],
            "checkpoint_path": checkpoint_ref(checkpoint), "checkpoint_sha256": execution["checkpoint"]["sha256"],
            "decision_thresholds": {"rule": "argmax over softmax per voxel"}, "held_out_predictions_path": checkpoint_ref(predictions),
            "evaluation_report_path": relative(report_path), "model_card_path": relative(MODEL_CARDS / f"{args.model_id}.md"),
        },
    })
    register_model(entry)
    print(json.dumps({"report": relative(report_path), "macro_dice": report["metrics"]["mean_case_macro_dice"],
                      "dice": {name: round(item["mean_dice"], 4) for name, item in per_structure.items()},
                      "lvef_mae": lvef["mean_absolute_error"], "lvef_bias": lvef["bias"]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
